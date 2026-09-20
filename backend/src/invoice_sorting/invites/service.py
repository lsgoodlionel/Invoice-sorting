"""邀请码业务：生成、列出与兑换。

兑换是公开入口，因此每一步都必须明确：邀请码本身有效、账套可用、
已有账号要验证密码、已是成员不重复加入。任何一步不通过都拒绝，不做“尽量成功”的补救。
"""

import secrets
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from invoice_sorting.auth.passwords import hash_password
from invoice_sorting.auth.service import Grant, authenticate, start_session
from invoice_sorting.common.errors import AppError, ConflictError
from invoice_sorting.config import Settings
from invoice_sorting.control.members import Member, find_member
from invoice_sorting.control.models import TENANT_STATUS_ACTIVE, Invite, Membership, Tenant
from invoice_sorting.control.repository import create_account, find_account, get_tenant
from invoice_sorting.db.models import now
from invoice_sorting.quota.members import ensure_member_capacity

CODE_BYTES = 12
DEFAULT_VALID_DAYS = 7

MSG_CODE_INVALID = "邀请码无效，请向管理员重新索取"
MSG_CODE_USED = "邀请码已被使用，请向管理员重新索取"
MSG_CODE_EXPIRED = "邀请码已过期，请向管理员重新索取"
MSG_TENANT_UNAVAILABLE = "该账套当前不可加入，请联系管理员"
MSG_ALREADY_MEMBER = "该账号已在此账套中，请直接登录"
MSG_WRONG_PASSWORD = "该用户名已存在，请填写它的登录密码"


@dataclass(frozen=True)
class JoinRequest:
    """兑换邀请码所需的信息。"""

    code: str
    username: str
    password: str
    display_name: str | None = None


def default_expiry(today: date | None = None) -> date:
    return (today or now().date()) + timedelta(days=DEFAULT_VALID_DAYS)


def create_invite(
    control: Session, tenant_id: int, role: str, expires_on: date | None = None
) -> Invite:
    invite = Invite(
        code=secrets.token_urlsafe(CODE_BYTES),
        tenant_id=tenant_id,
        role=role,
        expires_on=expires_on or default_expiry(),
    )
    control.add(invite)
    control.flush()
    return invite


def list_invites(control: Session, tenant_id: int) -> list[Invite]:
    return list(
        control.scalars(
            select(Invite).where(Invite.tenant_id == tenant_id).order_by(Invite.id.desc())
        )
    )


def _usable_invite(control: Session, code: str) -> Invite:
    invite = control.scalar(select(Invite).where(Invite.code == (code or "").strip()))
    if invite is None:
        raise AppError(MSG_CODE_INVALID, status_code=404)
    if invite.used_by is not None:
        raise ConflictError(MSG_CODE_USED)
    if invite.expires_on is not None and invite.expires_on < now().date():
        raise AppError(MSG_CODE_EXPIRED, status_code=410)
    return invite


def _usable_tenant(control: Session, tenant_id: int) -> Tenant:
    tenant = get_tenant(control, tenant_id)
    if tenant is None or tenant.status != TENANT_STATUS_ACTIVE:
        raise AppError(MSG_TENANT_UNAVAILABLE, status_code=403)
    return tenant


def _account_for(control: Session, request: JoinRequest):
    """已有账号必须验证密码；否则按该用户名新建账号。"""
    existing = find_account(control, request.username)
    if existing is None:
        return create_account(
            control,
            request.username,
            request.display_name or request.username,
            password_hash=hash_password(request.password),
        )
    if authenticate(control, request.username, request.password) is None:
        raise AppError(MSG_WRONG_PASSWORD, status_code=401)
    return existing


def redeem_invite(
    control: Session, request: JoinRequest, user_agent: str, settings: Settings | None = None
) -> Grant:
    """兑换邀请码：加入账套并直接登录到该账套。

    这是公开入口且前缀 `/api/auth/` 被写守卫豁免，因此成员数额度要在这里单独校验
    （传入 settings 才校验；不传表示调用方不启用额度，例如单元测试）。
    """
    invite = _usable_invite(control, request.code)
    tenant = _usable_tenant(control, invite.tenant_id)
    if settings is not None:
        ensure_member_capacity(settings, control, tenant)
    account = _account_for(control, request)
    if find_member(control, account.id, tenant.id) is not None:
        raise ConflictError(MSG_ALREADY_MEMBER)
    membership = Membership(account_id=account.id, tenant_id=tenant.id, role=invite.role)
    control.add(membership)
    invite.used_by = account.id
    invite.used_at = now()
    try:
        control.flush()
    except IntegrityError as exc:  # 并发兑换同一邀请码
        control.rollback()
        raise ConflictError(MSG_CODE_USED) from exc
    member = Member(account=account, membership=membership)
    return start_session(control, member, tenant, user_agent)
