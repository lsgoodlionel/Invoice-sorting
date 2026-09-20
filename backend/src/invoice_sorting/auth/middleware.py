"""认证中间件（纯 ASGI）：保护 /api/*（公开白名单除外），会话续期时追加 Set-Cookie。

校验通过后把当前用户写入 scope["state"]，并设置操作人上下文（见 auth/context.py）。
非 /api 路径（前端静态文件、SPA 回退）不拦截；settings.auth_enabled=False 时全部放行。

会话校验在**当前租户**的库中进行：先解析租户（见 tenancy/resolve.py），解析失败直接返回错误，
不会回退到任何默认库。
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker
from starlette.concurrency import run_in_threadpool
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from invoice_sorting.auth.context import AuthUser, reset_current_user, set_current_user
from invoice_sorting.auth.deps import STATE_USER_KEY
from invoice_sorting.auth.http import is_secure_request, read_session_token, session_cookie_header
from invoice_sorting.auth.service import MSG_LOGIN_REQUIRED, MSG_NEED_SETUP, is_password_set
from invoice_sorting.auth.sessions import validate_session
from invoice_sorting.common.errors import AppError
from invoice_sorting.tenancy.deps import tenant_for_connection

API_PREFIX = "/api"
PUBLIC_PATHS = frozenset({"/api/health", "/api/auth/status", "/api/auth/setup", "/api/auth/login"})


@dataclass(frozen=True)
class AccessDecision:
    error: str | None
    is_renewed: bool = False
    user: AuthUser | None = None


def is_protected_path(path: str) -> bool:
    is_api = path == API_PREFIX or path.startswith(f"{API_PREFIX}/")
    return is_api and path not in PUBLIC_PATHS


def decide_access(factory: sessionmaker[Session], token: str | None) -> AccessDecision:
    with factory() as db:
        if not is_password_set(db):
            return AccessDecision(error=MSG_NEED_SETUP)
        check = validate_session(db, token)
        db.commit()
    if not check.is_valid:
        return AccessDecision(error=MSG_LOGIN_REQUIRED)
    return AccessDecision(error=None, is_renewed=check.is_renewed, user=check.user)


def _error_response(message: str, status_code: int) -> JSONResponse:
    return JSONResponse({"ok": False, "data": None, "error": message}, status_code=status_code)


def _append_header(send: Send, name: bytes, value: bytes) -> Send:
    async def wrapped(message: Message) -> None:
        if message["type"] == "http.response.start":
            headers = [*message.get("headers", []), (name, value)]
            message = {**message, "headers": headers}
        await send(message)

    return wrapped


class AuthMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not is_protected_path(scope["path"]):
            await self.app(scope, receive, send)
            return
        state = scope["app"].state
        if not state.settings.auth_enabled:
            await self.app(scope, receive, send)
            return
        conn = HTTPConnection(scope)
        try:
            # 认证也必须在当前租户的库中进行，拿不到租户时直接失败（不回退默认库）
            tenant = await run_in_threadpool(tenant_for_connection, scope["app"], conn)
        except AppError as error:
            await _error_response(error.message, error.status_code)(scope, receive, send)
            return
        token = read_session_token(conn)
        decision = await run_in_threadpool(decide_access, tenant.session_factory, token)
        if decision.error is not None or decision.user is None:
            await _error_response(decision.error or MSG_LOGIN_REQUIRED, 401)(scope, receive, send)
            return
        if decision.is_renewed and token:
            cookie = session_cookie_header(token, is_secure_request(conn))
            send = _append_header(send, b"set-cookie", cookie)
        await self._call_as(decision.user, scope, receive, send)

    async def _call_as(self, user: AuthUser, scope: Scope, receive: Receive, send: Send) -> None:
        scope.setdefault("state", {})[STATE_USER_KEY] = user
        context_token = set_current_user(user.id)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_current_user(context_token)
