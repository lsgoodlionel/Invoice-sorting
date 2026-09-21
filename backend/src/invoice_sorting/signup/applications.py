"""提交申请与平台侧查询。

提交是公开入口：同一邮箱有待审批申请时 409；带推荐码时推荐人必须有效。
直接注册模式（平台关闭审批开关）下，推荐人本月名额未用完且已配置 SMTP 时自动批准并发信；
否则一律转为待审批——直接注册依赖邮件验证邮箱，发不了信就不能跳过审批。
"""

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from invoice_sorting.common.errors import ConflictError, NotFoundError
from invoice_sorting.control.signup_models import (
    APPLICATION_PENDING,
    APPLICATION_STATUSES,
    SignupApplication,
)
from invoice_sorting.signup.codes import hash_ip, normalize_email
from invoice_sorting.signup.constants import MSG_DUPLICATE_PENDING, WHAT_APPLICATION
from invoice_sorting.signup.provision import TenantOptions
from invoice_sorting.signup.referrals import Referrer, auto_approved_this_month, resolve_referrer
from invoice_sorting.signup.review import Delivery, Notifier, mark_approved, send_code
from invoice_sorting.signup.settings_store import load_settings

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class Submission:
    name: str
    email: str
    identity: str
    needs: str
    ledger_name: str = ""
    ref: str = ""
    ip: str = ""


@dataclass(frozen=True)
class SubmitResult:
    application: SignupApplication
    referrer_name: str = ""
    delivery: Delivery | None = None

    @property
    def is_auto_approved(self) -> bool:
        return self.delivery is not None


@dataclass(frozen=True)
class ApplicationPage:
    items: list[SignupApplication]
    total: int
    page: int
    page_size: int
    counts: dict[str, int]


def has_pending(control: Session, email: str) -> bool:
    query = select(SignupApplication.id).where(
        SignupApplication.email == email, SignupApplication.status == APPLICATION_PENDING
    )
    return control.scalar(query.limit(1)) is not None


def _can_auto_approve(control: Session, referrer: Referrer | None, notifier: Notifier) -> bool:
    if referrer is None or not notifier.mailer.is_configured:
        return False
    settings = load_settings(control)
    if settings.require_approval:
        return False
    used = auto_approved_this_month(control, referrer.account.id)
    return used < settings.monthly_referral_quota


def submit(control: Session, submission: Submission, notifier: Notifier) -> SubmitResult:
    email = normalize_email(submission.email)
    if has_pending(control, email):
        raise ConflictError(MSG_DUPLICATE_PENDING)
    referrer = resolve_referrer(control, submission.ref) if submission.ref else None
    is_auto = _can_auto_approve(control, referrer, notifier)
    application = SignupApplication(
        name=submission.name,
        email=email,
        identity=submission.identity,
        needs=submission.needs,
        ledger_name=submission.ledger_name,
        referrer_account_id=referrer.account.id if referrer else None,
        ip_hash=hash_ip(submission.ip, load_settings(control).ip_salt),
        is_auto_approved=is_auto,
    )
    control.add(application)
    control.flush()
    referrer_name = referrer.account.display_name if referrer else ""
    if not is_auto:
        return SubmitResult(application=application, referrer_name=referrer_name)
    mark_approved(control, application, TenantOptions(), reviewer_id=None)
    delivery = send_code(control, application, notifier)
    return SubmitResult(application=application, referrer_name=referrer_name, delivery=delivery)


def require_application(control: Session, application_id: int) -> SignupApplication:
    application = control.get(SignupApplication, application_id)
    if application is None:
        raise NotFoundError(WHAT_APPLICATION)
    return application


def _filtered(query, status: str, keyword: str):  # noqa: ANN001, ANN202 - SQLAlchemy 语句
    if status:
        query = query.where(SignupApplication.status == status)
    if keyword:
        like = f"%{keyword}%"
        query = query.where(
            or_(
                SignupApplication.name.like(like),
                SignupApplication.email.like(like),
                SignupApplication.identity.like(like),
            )
        )
    return query


def status_counts(control: Session) -> dict[str, int]:
    rows = control.execute(
        select(SignupApplication.status, func.count(SignupApplication.id)).group_by(
            SignupApplication.status
        )
    ).all()
    found = {status: int(count) for status, count in rows}
    return {status: found.get(status, 0) for status in APPLICATION_STATUSES}


def list_applications(
    control: Session,
    status: str = "",
    keyword: str = "",
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> ApplicationPage:
    """按提交时间倒序分页；counts 为各状态总数（不受筛选影响，供页签角标）。"""
    size = max(1, min(page_size, MAX_PAGE_SIZE))
    current = max(1, page)
    text = (keyword or "").strip()
    rows = _filtered(select(SignupApplication), status, text).order_by(SignupApplication.id.desc())
    counter = _filtered(select(func.count(SignupApplication.id)), status, text)
    items = list(control.scalars(rows.offset((current - 1) * size).limit(size)))
    total = int(control.scalar(counter) or 0)
    counts = status_counts(control)
    return ApplicationPage(items=items, total=total, page=current, page_size=size, counts=counts)
