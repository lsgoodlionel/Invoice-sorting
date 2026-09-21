"""凭注册码完成注册：创建账号 + 开通独立账套（本人为管理员）+ 签发会话。

开通复用 platform_admin.tenants.open_tenant，会话复用 auth.service.start_session。
注册码一次性、绑定申请邮箱、有过期时间；用条件 UPDATE 抢占，同一个码并发注册只有一个成功。
"""

from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from invoice_sorting.auth.service import Grant, start_session
from invoice_sorting.common.errors import AppError, ConflictError
from invoice_sorting.control.members import Member
from invoice_sorting.control.repository import MSG_USERNAME_TAKEN, find_account
from invoice_sorting.control.signup_models import (
    APPLICATION_APPROVED,
    APPLICATION_REGISTERED,
    SignupApplication,
)
from invoice_sorting.db.models import now
from invoice_sorting.platform_admin.schemas import TenantCreate
from invoice_sorting.platform_admin.tenants import open_tenant
from invoice_sorting.signup.codes import aware, hash_code, normalize_email
from invoice_sorting.signup.constants import (
    MSG_CODE_EXPIRED,
    MSG_CODE_INVALID,
    MSG_CODE_USED,
    MSG_EMAIL_MISMATCH,
    NAME_MAX,
)
from invoice_sorting.signup.provision import auto_slug, is_slug_free


@dataclass(frozen=True)
class RegistrationForm:
    code: str
    email: str
    username: str
    password: str
    display_name: str | None = None


def find_by_code(control: Session, code: str) -> SignupApplication | None:
    if not (code or "").strip():
        return None
    return control.scalar(
        select(SignupApplication).where(SignupApplication.code_hash == hash_code(code))
    )


def usable_application(control: Session, code: str) -> SignupApplication:
    """注册码有效时返回对应申请；无效 404、已使用 409、已过期 410。"""
    application = find_by_code(control, code)
    if application is None or application.status not in (
        APPLICATION_APPROVED,
        APPLICATION_REGISTERED,
    ):
        raise AppError(MSG_CODE_INVALID, status_code=404)
    if application.status == APPLICATION_REGISTERED:
        raise ConflictError(MSG_CODE_USED)
    expires_at = aware(application.code_expires_at)
    if expires_at is None or expires_at <= now():
        raise AppError(MSG_CODE_EXPIRED, status_code=410)
    return application


def _claim(control: Session, application: SignupApplication, code: str) -> None:
    """条件更新：只有仍处于“已批准”且码未被换发时才能占用，否则按已使用处理。"""
    statement = (
        update(SignupApplication)
        .where(
            SignupApplication.id == application.id,
            SignupApplication.status == APPLICATION_APPROVED,
            SignupApplication.code_hash == hash_code(code),
        )
        .values(status=APPLICATION_REGISTERED, registered_at=now())
        .execution_options(synchronize_session=False)
    )
    if control.execute(statement).rowcount != 1:
        raise ConflictError(MSG_CODE_USED)
    control.refresh(application)


def _tenant_body(control: Session, application: SignupApplication, form: RegistrationForm):
    slug = application.approved_slug
    if not slug or not is_slug_free(control, slug, application.id):
        slug = auto_slug(control, application.email, application.id)  # 批准后被别人占用时兜底
    display_name = (form.display_name or application.name or form.username)[:NAME_MAX]
    return TenantCreate(
        slug=slug,
        name=application.approved_name or None,
        plan_code=application.approved_plan_code or None,
        expires_on=application.approved_expires_on,
        admin_username=form.username,
        admin_password=form.password,
        admin_display_name=display_name,
    )


def complete_registration(control: Session, form: RegistrationForm, user_agent: str) -> Grant:
    application = usable_application(control, form.code)
    if normalize_email(form.email) != application.email:
        raise AppError(MSG_EMAIL_MISMATCH, status_code=400)
    # 已存在的用户名必须拒绝：open_tenant 会把同名旧账号直接加进新账套，等于越权接管
    if find_account(control, form.username) is not None:
        raise ConflictError(MSG_USERNAME_TAKEN)
    body = _tenant_body(control, application, form)
    _claim(control, application, form.code)
    opened = open_tenant(control, body)
    member: Member | None = opened.member
    if member is None:  # 传了管理员用户名就一定会开通；防御性检查
        raise AppError(MSG_CODE_INVALID, status_code=500)
    application.registered_account_id = member.id
    application.registered_tenant_id = opened.tenant.id
    control.flush()
    return start_session(control, member, opened.tenant, user_agent)
