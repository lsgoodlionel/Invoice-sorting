"""登录用户的推荐链接（/api/referrals/me）：首次打开自动生成推荐码，可重置。

推荐人只能看到自己推荐了几人与各自状态（邮箱脱敏），看不到被推荐人的需求等资料。
推荐码属于账号而非账套：无论当前在哪个账套，看到的都是同一个。
"""

from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy.orm import Session

from invoice_sorting.auth.context import AuthUser
from invoice_sorting.auth.deps import CurrentUserDep
from invoice_sorting.common.errors import AppError, ok
from invoice_sorting.control.deps import ControlSessionDep
from invoice_sorting.control.signup_models import ReferralCode
from invoice_sorting.signup.constants import MSG_LOGIN_REQUIRED, REFERRALS_API
from invoice_sorting.signup.deps import SAAS_ONLY, resolved_mail_of
from invoice_sorting.signup.notices import referral_link
from invoice_sorting.signup.referrals import (
    auto_approved_this_month,
    ensure_referral,
    referred_applications,
    reset_referral,
)
from invoice_sorting.signup.serializers import serialize_my_referral
from invoice_sorting.signup.settings_store import load_settings

router = APIRouter(prefix=REFERRALS_API, tags=["推荐好友"], dependencies=SAAS_ONLY)


def _require_user(user: AuthUser | None) -> AuthUser:
    if user is None:
        raise AppError(MSG_LOGIN_REQUIRED, status_code=401)
    return user


def _my_referral(request: Request, control: Session, referral: ReferralCode) -> dict[str, Any]:
    settings = load_settings(control)
    referred = referred_applications(control, referral.account_id)
    is_usable = not referral.is_disabled
    base_url = resolved_mail_of(request, control).base_url
    return {
        "code": referral.code if is_usable else None,
        "link": referral_link(base_url, referral.code) if is_usable else None,
        "is_disabled": referral.is_disabled,
        "require_approval": settings.require_approval,
        "monthly_quota": settings.monthly_referral_quota,
        "used_this_month": auto_approved_this_month(control, referral.account_id),
        "total": len(referred),
        "referrals": [serialize_my_referral(item) for item in referred],
    }


@router.get("/me")
def read_my_referral(
    request: Request, control: ControlSessionDep, user: CurrentUserDep
) -> dict[str, Any]:
    referral = ensure_referral(control, _require_user(user).id)
    return ok(_my_referral(request, control, referral))


@router.post("/me/reset")
def post_reset_referral(
    request: Request, control: ControlSessionDep, user: CurrentUserDep
) -> dict[str, Any]:
    """换发新推荐码，旧链接立即失效；推荐资格被停用时 403。"""
    referral = reset_referral(control, _require_user(user).id)
    return ok(_my_referral(request, control, referral))
