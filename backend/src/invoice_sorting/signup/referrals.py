"""推荐码：每个账号一个，首次查看时自动生成；可重置（旧链接立即失效），平台可停用。"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from invoice_sorting.common.errors import AppError, NotFoundError
from invoice_sorting.control.models import Account
from invoice_sorting.control.signup_models import ReferralCode, SignupApplication
from invoice_sorting.db.models import now
from invoice_sorting.signup.codes import new_referral_code, normalize_referral_code
from invoice_sorting.signup.constants import (
    MSG_REFERRAL_DISABLED,
    MSG_REFERRAL_INVALID,
    WHAT_ACCOUNT,
)

MAX_CODE_ATTEMPTS = 5


@dataclass(frozen=True)
class Referrer:
    """推荐码对应的有效推荐人。"""

    account: Account
    referral: ReferralCode


def find_referral(control: Session, account_id: int) -> ReferralCode | None:
    return control.scalar(select(ReferralCode).where(ReferralCode.account_id == account_id))


def _unused_code(control: Session) -> str:
    for _ in range(MAX_CODE_ATTEMPTS):
        code = new_referral_code()
        if control.scalar(select(ReferralCode.id).where(ReferralCode.code == code)) is None:
            return code
    raise AppError("推荐码生成失败，请稍后再试", status_code=503)


def ensure_referral(control: Session, account_id: int) -> ReferralCode:
    """取本人的推荐码，没有就生成一个。调用方负责提交。"""
    found = find_referral(control, account_id)
    if found is not None:
        return found
    referral = ReferralCode(account_id=account_id, code=_unused_code(control))
    control.add(referral)
    try:
        control.flush()
    except IntegrityError:  # 同一账号并发首次打开：以先写入的为准
        control.rollback()
        winner = find_referral(control, account_id)
        if winner is None:
            raise
        return winner
    return referral


def reset_referral(control: Session, account_id: int) -> ReferralCode:
    """换发新推荐码；推荐资格被停用时 403。"""
    referral = ensure_referral(control, account_id)
    if referral.is_disabled:
        raise AppError(MSG_REFERRAL_DISABLED, status_code=403)
    referral.code = _unused_code(control)
    referral.reset_at = now()
    control.flush()
    return referral


def set_referral_disabled(control: Session, account_id: int, is_disabled: bool) -> ReferralCode:
    """平台停用/恢复某人的推荐资格；账号不存在时 404。"""
    if control.get(Account, account_id) is None:
        raise NotFoundError(WHAT_ACCOUNT)
    referral = ensure_referral(control, account_id)
    referral.is_disabled = is_disabled
    control.flush()
    return referral


def resolve_referrer(control: Session, code: str) -> Referrer:
    """按推荐码找到有效推荐人；码不存在、被停用或账号已停用一律 404（不区分原因）。"""
    normalized = normalize_referral_code(code)
    referral = (
        control.scalar(select(ReferralCode).where(ReferralCode.code == normalized))
        if normalized
        else None
    )
    account = control.get(Account, referral.account_id) if referral is not None else None
    if referral is None or referral.is_disabled or account is None or not account.is_active:
        raise AppError(MSG_REFERRAL_INVALID, status_code=404)
    return Referrer(account=account, referral=referral)


def month_start(moment: datetime | None = None) -> datetime:
    current = moment or now()
    return current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def auto_approved_this_month(control: Session, account_id: int) -> int:
    """本月已占用的直接注册名额（自动批准的推荐申请数）。"""
    query = select(func.count(SignupApplication.id)).where(
        SignupApplication.referrer_account_id == account_id,
        SignupApplication.is_auto_approved.is_(True),
        SignupApplication.created_at >= month_start(),
    )
    return int(control.scalar(query) or 0)


def referred_applications(control: Session, account_id: int) -> list[SignupApplication]:
    query = (
        select(SignupApplication)
        .where(SignupApplication.referrer_account_id == account_id)
        .order_by(SignupApplication.id.desc())
    )
    return list(control.scalars(query))


@dataclass(frozen=True)
class RecordPage:
    items: list[SignupApplication]
    total: int
    page: int
    page_size: int


def _record_filter(query, keyword: str):  # noqa: ANN001, ANN202 - SQLAlchemy 语句
    query = query.join(Account, Account.id == SignupApplication.referrer_account_id)
    if not keyword:
        return query
    like = f"%{keyword}%"
    return query.where(
        or_(
            SignupApplication.email.like(like),
            Account.username.like(like),
            Account.display_name.like(like),
        )
    )


def list_referral_records(control: Session, keyword: str, page: int, page_size: int) -> RecordPage:
    """所有带推荐人的申请，按时间倒序；可按被推荐人邮箱或推荐人账号、姓名搜索。"""
    text = (keyword or "").strip()
    rows = _record_filter(select(SignupApplication), text).order_by(SignupApplication.id.desc())
    counter = _record_filter(select(func.count(SignupApplication.id)), text)
    items = list(control.scalars(rows.offset((page - 1) * page_size).limit(page_size)))
    total = int(control.scalar(counter) or 0)
    return RecordPage(items=items, total=total, page=page, page_size=page_size)
