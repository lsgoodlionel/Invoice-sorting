"""平台邮件设置接口（仅平台管理员，仅多账套部署；单账套 404）。

测试连接与测试邮件都使用**当前已保存并生效的配置**（环境变量优先，其次网页配置），
不接受请求体里临时带的配置——页面上有未保存的修改时需先保存再测试，结果与实际发信一致。
"""

from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy.orm import Session

from invoice_sorting.auth.context import AuthUser
from invoice_sorting.auth.deps import CurrentUserDep
from invoice_sorting.auth.ratelimit import LoginRateLimiter, minutes_label
from invoice_sorting.common.errors import AppError, ok
from invoice_sorting.control.deps import ControlSessionDep
from invoice_sorting.control.platform_deps import PLATFORM_ADMIN_ONLY
from invoice_sorting.mail_settings.checks import CheckOutcome, check_connection, send_test_email
from invoice_sorting.mail_settings.constants import (
    CHECK_CONNECTION,
    CHECK_EMAIL,
    MAIL_SETTINGS_PATH,
    MSG_ENV_READONLY,
    MSG_NOT_CONFIGURED,
    MSG_TOO_FREQUENT,
    TEST_CONNECTION_MAX_PER_WINDOW,
    TEST_CONNECTION_WINDOW_SECONDS,
    TEST_EMAIL_MAX_PER_WINDOW,
    TEST_EMAIL_WINDOW_SECONDS,
)
from invoice_sorting.mail_settings.schemas import MailSettingsPatch, TestEmailBody
from invoice_sorting.mail_settings.serializers import serialize_check, serialize_mail_settings
from invoice_sorting.mail_settings.store import MailChange, record_check, update_mail_settings
from invoice_sorting.mailer.resolve import SOURCE_ENV, mail_row
from invoice_sorting.mailer.service import MailConfig
from invoice_sorting.signup.deps import SAAS_ONLY, mailer_factory_of, resolved_mail_of

STATE_TEST_EMAIL_LIMITER = "mail_test_email_limiter"
STATE_TEST_CONNECTION_LIMITER = "mail_test_connection_limiter"

router = APIRouter(
    prefix=f"/api/platform{MAIL_SETTINGS_PATH}",
    tags=["平台邮件设置"],
    dependencies=[*SAAS_ONLY, *PLATFORM_ADMIN_ONLY],
)


def install_mail_settings_state(app: Any) -> None:
    """两个测试接口按平台管理员限流：每次调用都计数（限的是频率，不只是失败）。"""
    limiters = {
        STATE_TEST_EMAIL_LIMITER: (TEST_EMAIL_MAX_PER_WINDOW, TEST_EMAIL_WINDOW_SECONDS),
        STATE_TEST_CONNECTION_LIMITER: (
            TEST_CONNECTION_MAX_PER_WINDOW,
            TEST_CONNECTION_WINDOW_SECONDS,
        ),
    }
    for name, (limit, window) in limiters.items():
        limiter = LoginRateLimiter(max_failures=limit, window_seconds=window, lock_seconds=window)
        setattr(app.state, name, limiter)


def _operator_id(user: AuthUser | None) -> int | None:
    return user.id if user is not None else None


def _consume(request: Request, name: str, user: AuthUser | None) -> None:
    limiter: LoginRateLimiter = getattr(request.app.state, name)
    key = f"account:{_operator_id(user)}"
    wait = limiter.retry_after(key)
    if wait:
        raise AppError(MSG_TOO_FREQUENT.format(minutes=minutes_label(wait)), status_code=429)
    limiter.record_failure(key)


def _current(request: Request, control: Session) -> dict[str, Any]:
    resolved = resolved_mail_of(request, control)
    settings = request.app.state.settings
    return serialize_mail_settings(control, settings, mail_row(control), resolved)


def _effective_config(request: Request, control: Session) -> MailConfig:
    config = resolved_mail_of(request, control).config
    if config is None:
        raise AppError(MSG_NOT_CONFIGURED, status_code=409)
    return config


def _recorded(control: Session, kind: str, outcome: CheckOutcome, user: AuthUser | None):
    row = record_check(control, kind, outcome.info, outcome.is_ok, _operator_id(user))
    return ok(serialize_check(row, outcome.is_ok))


@router.get("")
def read_mail_settings(request: Request, control: ControlSessionDep) -> dict[str, Any]:
    return ok(_current(request, control))


@router.patch("")
def patch_mail_settings(
    body: MailSettingsPatch, request: Request, control: ControlSessionDep, user: CurrentUserDep
) -> dict[str, Any]:
    if resolved_mail_of(request, control).source == SOURCE_ENV:
        raise AppError(MSG_ENV_READONLY, status_code=409)
    change = MailChange(**body.model_dump())
    update_mail_settings(control, request.app.state.settings, change, _operator_id(user))
    return ok(_current(request, control))


@router.post("/test-connection")
def post_test_connection(
    request: Request, control: ControlSessionDep, user: CurrentUserDep
) -> dict[str, Any]:
    config = _effective_config(request, control)
    _consume(request, STATE_TEST_CONNECTION_LIMITER, user)
    outcome = check_connection(mailer_factory_of(request), config)
    return _recorded(control, CHECK_CONNECTION, outcome, user)


@router.post("/test-email")
def post_test_email(
    body: TestEmailBody, request: Request, control: ControlSessionDep, user: CurrentUserDep
) -> dict[str, Any]:
    config = _effective_config(request, control)
    _consume(request, STATE_TEST_EMAIL_LIMITER, user)
    outcome = send_test_email(mailer_factory_of(request), config, body.to)
    return _recorded(control, CHECK_EMAIL, outcome, user)
