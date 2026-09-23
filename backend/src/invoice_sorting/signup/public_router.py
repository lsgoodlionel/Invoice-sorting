"""公开入口（/api/signup/*，已加入认证白名单）：提交申请、校验推荐码与注册码、完成注册。

只在多账套部署开放；单账套部署一律 404。
- 提交申请按 IP 每小时 5 次（每次提交都计数，不论成败）；
- 推荐码与注册码的校验、凭码注册按 IP 统计失败次数，防止穷举。
"""

import secrets
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Query, Request, Response
from sqlalchemy.orm import Session

from invoice_sorting.attachments.serializers import iso_datetime
from invoice_sorting.auth.http import USER_AGENT_HEADER, client_ip
from invoice_sorting.auth.router import grant_response
from invoice_sorting.common.errors import AppError, ok
from invoice_sorting.control.deps import ControlSessionDep
from invoice_sorting.control.signup_models import APPLICATION_PENDING
from invoice_sorting.signup.applications import Submission, SubmitResult, submit
from invoice_sorting.signup.codes import application_number
from invoice_sorting.signup.constants import (
    MSG_SUBMITTED,
    MSG_SUBMITTED_DIRECT,
    REGISTER_CODE_MAX,
    SIGNUP_API,
)
from invoice_sorting.signup.deps import (
    SAAS_ONLY,
    STATE_APPLY_LIMITER,
    STATE_CODE_LIMITER,
    ensure_not_limited,
    limiter_of,
    notifier_of,
)
from invoice_sorting.signup.notify import schedule_pending_alert
from invoice_sorting.signup.referrals import resolve_referrer
from invoice_sorting.signup.register import (
    RegistrationForm,
    complete_registration,
    usable_application,
)
from invoice_sorting.signup.schemas import ApplyBody, RegisterBody
from invoice_sorting.signup.settings_store import load_settings

router = APIRouter(prefix=SIGNUP_API, tags=["注册申请"], dependencies=SAAS_ONLY)

DECOY_ID_MAX = 999_999


def _submitted(result: SubmitResult) -> dict[str, Any]:
    application = result.application
    return {
        "id": application.id,
        "number": application_number(application.id),
        "status": application.status,
        "referrer_name": result.referrer_name or None,
        "message": MSG_SUBMITTED_DIRECT if result.is_auto_approved else MSG_SUBMITTED,
    }


def _decoy() -> dict[str, Any]:
    """诱饵字段被填写：返回与正常提交同样形状的结果，但什么都不写入。"""
    fake_id = secrets.randbelow(DECOY_ID_MAX) + 1
    return {
        "id": fake_id,
        "number": application_number(fake_id),
        "status": APPLICATION_PENDING,
        "referrer_name": None,
        "message": MSG_SUBMITTED,
    }


@router.post("/applications")
def post_application(
    body: ApplyBody, request: Request, background: BackgroundTasks, control: ControlSessionDep
):
    limiter = limiter_of(request, STATE_APPLY_LIMITER)
    key = ensure_not_limited(request, limiter)
    limiter.record_failure(key)  # 每次提交都计数：限的是提交频率，不只是失败
    if body.website:
        return ok(_decoy())
    submission = Submission(
        name=body.name,
        email=body.email,
        identity=body.identity,
        needs=body.needs,
        ledger_name=body.ledger_name,
        ref=body.ref,
        ip=client_ip(request),
    )
    result = submit(control, submission, notifier_of(request, control))
    if result.application.status == APPLICATION_PENDING:
        # 待审批才提醒平台；直接注册模式下自动批准的那些不打扰
        schedule_pending_alert(request, background, control, result.application.id)
    return ok(_submitted(result))


def _guarded(request: Request, action):  # noqa: ANN001, ANN202 - 包装一次码校验
    """码校验失败计入该 IP 的失败次数；成功不清零（防止穿插一次成功来重置计数）。"""
    limiter = limiter_of(request, STATE_CODE_LIMITER)
    key = ensure_not_limited(request, limiter)
    try:
        return action()
    except AppError:
        limiter.record_failure(key)
        raise


@router.get("/referral/{code}")
def read_referral(code: str, request: Request, control: ControlSessionDep) -> dict[str, Any]:
    """校验推荐码：返回推荐人显示名，申请表据此预填且不可修改。"""
    referrer = _guarded(request, lambda: resolve_referrer(control, code))
    return ok(
        {
            "code": referrer.referral.code,
            "referrer_name": referrer.account.display_name,
            "require_approval": load_settings(control).require_approval,
        }
    )


@router.get("/register")
def read_register(
    request: Request,
    control: ControlSessionDep,
    code: str = Query("", max_length=REGISTER_CODE_MAX),
) -> dict[str, Any]:
    """校验注册码：返回申请邮箱（注册页只读显示）、姓名、账本名与有效期。"""
    application = _guarded(request, lambda: usable_application(control, code))
    return ok(
        {
            "email": application.email,
            "name": application.name,
            "ledger_name": application.approved_name,
            "expires_at": iso_datetime(application.code_expires_at),
        }
    )


def _register(request: Request, control: Session, body: RegisterBody):  # noqa: ANN202
    form = RegistrationForm(
        code=body.code,
        email=body.email,
        username=body.username,
        password=body.password,
        display_name=body.display_name,
    )
    agent = request.headers.get(USER_AGENT_HEADER, "")
    return _guarded(request, lambda: complete_registration(control, form, agent))


@router.post("/register")
def post_register(
    body: RegisterBody, request: Request, response: Response, control: ControlSessionDep
) -> dict[str, Any]:
    """完成注册：创建账号、开通独立账套（本人为管理员）并直接登录。"""
    grant = _register(request, control, body)
    return grant_response(request, response, control, grant)
