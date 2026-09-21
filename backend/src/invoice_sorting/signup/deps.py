"""注册申请相关依赖：只在多账套部署开放，单账套一律 404；发信服务与限流器的取用。"""

from typing import Any

from fastapi import Depends, Request

from invoice_sorting.auth.http import client_ip
from invoice_sorting.auth.ratelimit import LoginRateLimiter, minutes_label
from invoice_sorting.common.errors import AppError
from invoice_sorting.mailer.service import STATE_MAILER_KEY, Mailer
from invoice_sorting.signup.constants import (
    APPLY_MAX_PER_WINDOW,
    APPLY_WINDOW_SECONDS,
    CODE_MAX_FAILURES,
    CODE_WINDOW_SECONDS,
    MSG_SAAS_ONLY,
    MSG_TOO_FREQUENT,
)
from invoice_sorting.signup.review import Notifier

STATE_APPLY_LIMITER = "signup_apply_limiter"
STATE_CODE_LIMITER = "signup_code_limiter"


def require_saas(request: Request) -> None:
    """单账套部署没有注册申请与推荐：所有入口 404，界面也不出现。"""
    if not request.app.state.settings.is_saas:
        raise AppError(MSG_SAAS_ONLY, status_code=404)


SAAS_ONLY = [Depends(require_saas)]


def install_signup_state(app: Any, mailer: Mailer) -> None:
    """装配发信服务与两个限流器（申请提交按次数计，码校验按失败次数计）。"""
    setattr(app.state, STATE_MAILER_KEY, mailer)
    setattr(
        app.state,
        STATE_APPLY_LIMITER,
        LoginRateLimiter(
            max_failures=APPLY_MAX_PER_WINDOW,
            window_seconds=APPLY_WINDOW_SECONDS,
            lock_seconds=APPLY_WINDOW_SECONDS,
        ),
    )
    setattr(
        app.state,
        STATE_CODE_LIMITER,
        LoginRateLimiter(max_failures=CODE_MAX_FAILURES, window_seconds=CODE_WINDOW_SECONDS),
    )


def notifier_of(request: Request) -> Notifier:
    app = request.app
    return Notifier(
        mailer=getattr(app.state, STATE_MAILER_KEY),
        base_url=app.state.settings.public_base_url,
    )


def limiter_of(request: Request, name: str) -> LoginRateLimiter:
    return getattr(request.app.state, name)


def ensure_not_limited(request: Request, limiter: LoginRateLimiter) -> str:
    """仍在限制期内时 429；否则返回本次请求的限流键（客户端 IP）。"""
    key = client_ip(request)
    wait = limiter.retry_after(key)
    if wait:
        raise AppError(MSG_TOO_FREQUENT.format(minutes=minutes_label(wait)), status_code=429)
    return key
