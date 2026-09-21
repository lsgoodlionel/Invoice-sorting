"""平台运营后台：注册申请审批、推荐记录与注册设置（仅平台管理员，仅多账套部署）。

审批操作记录操作人与时间；通知没发出去时，响应里带注册链接与通知文字供管理员转告。
"""

from typing import Any

from fastapi import APIRouter, Query, Request
from sqlalchemy.orm import Session

from invoice_sorting.auth.context import AuthUser
from invoice_sorting.auth.deps import CurrentUserDep
from invoice_sorting.common.errors import ok
from invoice_sorting.control.deps import ControlSessionDep
from invoice_sorting.control.platform_deps import PLATFORM_ADMIN_ONLY
from invoice_sorting.control.signup_models import APPLICATION_STATUSES, SignupApplication
from invoice_sorting.signup.applications import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    list_applications,
    require_application,
)
from invoice_sorting.signup.constants import SEARCH_MAX
from invoice_sorting.signup.deps import SAAS_ONLY, notifier_of
from invoice_sorting.signup.provision import TenantOptions
from invoice_sorting.signup.referrals import list_referral_records, set_referral_disabled
from invoice_sorting.signup.review import ReviewResult, approve, reject, resend
from invoice_sorting.signup.schemas import (
    ApproveBody,
    ReferrerPatch,
    RejectBody,
    SignupSettingsPatch,
)
from invoice_sorting.signup.serializers import (
    build_lookup,
    serialize_application,
    serialize_delivery,
    serialize_referral_record,
    serialize_settings,
)
from invoice_sorting.signup.settings_store import SettingsChange, load_settings, update_settings

router = APIRouter(
    prefix="/api/platform", tags=["平台注册申请"], dependencies=[*SAAS_ONLY, *PLATFORM_ADMIN_ONLY]
)

STATUS_PATTERN = "^(" + "|".join(APPLICATION_STATUSES) + ")?$"


def _one(control: Session, item: SignupApplication) -> dict[str, Any]:
    return serialize_application(item, build_lookup(control, [item]))


def _reviewed(control: Session, result: ReviewResult) -> dict[str, Any]:
    return {
        "application": _one(control, result.application),
        "notice": serialize_delivery(result.delivery),
    }


def _operator_id(user: AuthUser | None) -> int | None:
    return user.id if user is not None else None


@router.get("/applications")
def read_applications(
    control: ControlSessionDep,
    status: str = Query("", pattern=STATUS_PATTERN),
    q: str = Query("", max_length=SEARCH_MAX),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> dict[str, Any]:
    result = list_applications(control, status, q, page, page_size)
    lookup = build_lookup(control, result.items)
    return ok(
        {
            "items": [serialize_application(item, lookup) for item in result.items],
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
            "counts": result.counts,
        }
    )


@router.get("/applications/{application_id}")
def read_application(application_id: int, control: ControlSessionDep) -> dict[str, Any]:
    return ok(_one(control, require_application(control, application_id)))


@router.post("/applications/{application_id}/approve")
def post_approve(
    application_id: int,
    body: ApproveBody,
    request: Request,
    control: ControlSessionDep,
    user: CurrentUserDep,
) -> dict[str, Any]:
    options = TenantOptions(
        slug=body.slug, name=body.name, plan_code=body.plan_code, expires_on=body.expires_on
    )
    application = require_application(control, application_id)
    result = approve(control, application, options, _operator_id(user), notifier_of(request))
    return ok(_reviewed(control, result))


@router.post("/applications/{application_id}/reject")
def post_reject(
    application_id: int,
    body: RejectBody,
    request: Request,
    control: ControlSessionDep,
    user: CurrentUserDep,
) -> dict[str, Any]:
    application = require_application(control, application_id)
    result = reject(control, application, body.reason, _operator_id(user), notifier_of(request))
    return ok(_reviewed(control, result))


@router.post("/applications/{application_id}/resend")
def post_resend(
    application_id: int, request: Request, control: ControlSessionDep, user: CurrentUserDep
) -> dict[str, Any]:
    """已批准待注册：换发新注册码（旧链接失效）并重发；已否决：重发否决通知。"""
    application = require_application(control, application_id)
    result = resend(control, application, notifier_of(request), _operator_id(user))
    return ok(_reviewed(control, result))


@router.get("/referrals")
def read_referral_records(
    control: ControlSessionDep,
    q: str = Query("", max_length=SEARCH_MAX),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> dict[str, Any]:
    result = list_referral_records(control, q, page, page_size)
    lookup = build_lookup(control, result.items)
    return ok(
        {
            "items": [serialize_referral_record(item, lookup) for item in result.items],
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
        }
    )


@router.patch("/referrers/{account_id}")
def patch_referrer(account_id: int, body: ReferrerPatch, control: ControlSessionDep):
    """停用或恢复某人的推荐资格；停用后其推荐链接立即失效。"""
    referral = set_referral_disabled(control, account_id, body.is_disabled)
    return ok({"account_id": referral.account_id, "is_disabled": referral.is_disabled})


@router.get("/signup-settings")
def read_signup_settings(request: Request, control: ControlSessionDep) -> dict[str, Any]:
    is_mail = notifier_of(request).mailer.is_configured
    return ok(serialize_settings(load_settings(control), is_mail))


@router.patch("/signup-settings")
def patch_signup_settings(
    body: SignupSettingsPatch, request: Request, control: ControlSessionDep, user: CurrentUserDep
) -> dict[str, Any]:
    change = SettingsChange(
        require_approval=body.require_approval,
        monthly_referral_quota=body.monthly_referral_quota,
        code_valid_days=body.code_valid_days,
    )
    row = update_settings(control, change, _operator_id(user))
    return ok(serialize_settings(row, notifier_of(request).mailer.is_configured))
