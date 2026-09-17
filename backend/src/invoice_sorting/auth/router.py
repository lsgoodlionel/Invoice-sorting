"""认证 API：状态、设置初始密码、登录、退出、修改密码。"""

from typing import Any

from fastapi import APIRouter, Request, Response

from invoice_sorting.auth.http import (
    USER_AGENT_HEADER,
    clear_session_cookie,
    client_ip,
    is_secure_request,
    read_session_token,
    set_session_cookie,
)
from invoice_sorting.auth.ratelimit import LoginRateLimiter, minutes_label
from invoice_sorting.auth.schemas import ChangePasswordBody, LoginBody, SetupBody
from invoice_sorting.auth.service import (
    MSG_WRONG_PASSWORD,
    change_password,
    is_password_set,
    login_with_password,
    setup_initial_password,
)
from invoice_sorting.auth.sessions import delete_session, validate_session
from invoice_sorting.common.errors import AppError, ok
from invoice_sorting.settings.deps import ConfigDep, SessionDep

router = APIRouter(prefix="/api/auth", tags=["登录认证"])


def _user_agent(request: Request) -> str:
    return request.headers.get(USER_AGENT_HEADER, "")


def _grant(request: Request, response: Response, token: str) -> dict[str, Any]:
    set_session_cookie(response, token, is_secure_request(request))
    return ok({"authenticated": True})


@router.get("/status")
def auth_status(
    request: Request, response: Response, session: SessionDep, config: ConfigDep
) -> dict[str, Any]:
    password_set = is_password_set(session)
    authenticated = True
    if config.auth_enabled:
        token = read_session_token(request)
        check = validate_session(session, token)
        authenticated = password_set and check.is_valid
        if check.is_renewed and token:
            set_session_cookie(response, token, is_secure_request(request))
    return ok(
        {
            "auth_enabled": config.auth_enabled,
            "password_set": password_set,
            "authenticated": authenticated,
        }
    )


@router.post("/setup")
def auth_setup(
    body: SetupBody, request: Request, response: Response, session: SessionDep
) -> dict[str, Any]:
    token = setup_initial_password(session, body.password, _user_agent(request))
    return _grant(request, response, token)


@router.post("/login")
def auth_login(
    body: LoginBody, request: Request, response: Response, session: SessionDep
) -> dict[str, Any]:
    limiter: LoginRateLimiter = request.app.state.login_limiter
    key = client_ip(request)
    wait = limiter.retry_after(key)
    if wait:
        raise AppError(f"尝试次数过多，请 {minutes_label(wait)} 分钟后再试", status_code=429)
    token = login_with_password(session, body.password, _user_agent(request))
    if token is None:
        limiter.record_failure(key)
        raise AppError(MSG_WRONG_PASSWORD, status_code=401)
    limiter.reset(key)
    return _grant(request, response, token)


@router.post("/logout")
def auth_logout(request: Request, response: Response, session: SessionDep) -> dict[str, Any]:
    delete_session(session, read_session_token(request))
    clear_session_cookie(response, is_secure_request(request))
    return ok(None)


@router.post("/password")
def auth_change_password(
    body: ChangePasswordBody, request: Request, session: SessionDep
) -> dict[str, Any]:
    token = read_session_token(request)
    change_password(session, body.current_password, body.new_password, token)
    return ok(None)
