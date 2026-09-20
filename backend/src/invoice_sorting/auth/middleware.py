"""认证中间件（纯 ASGI）：保护 /api/*（公开白名单除外），会话续期时追加 Set-Cookie。

校验通过后把当前用户写入 scope["state"]，并设置操作人上下文（见 auth/context.py）。
非 /api 路径（前端静态文件、SPA 回退）不拦截；settings.auth_enabled=False 时全部放行。

顺序很关键：
1. 先在**控制库**按会话令牌取出所选租户，写入 scope state（租户解析据此接手）；
2. 再解析租户（子域名优先，见 tenancy/resolve.py），解析不到直接失败，不回退默认库；
3. 最后在控制库校验会话与该租户的成员关系——不是成员一律 403。
"""

from dataclasses import dataclass
from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from invoice_sorting.auth.context import AuthUser, reset_current_user, set_current_user
from invoice_sorting.auth.deps import STATE_USER_KEY
from invoice_sorting.auth.http import is_secure_request, read_session_token, session_cookie_header
from invoice_sorting.auth.service import MSG_LOGIN_REQUIRED, MSG_NEED_SETUP, is_password_set
from invoice_sorting.auth.sessions import validate_session
from invoice_sorting.auth.tenants import session_tenant_slug
from invoice_sorting.common.errors import AppError
from invoice_sorting.control.deps import require_tenant_row
from invoice_sorting.licensing.constants import LICENSE_VERIFY_PATH
from invoice_sorting.tenancy.deps import tenant_for_connection
from invoice_sorting.tenancy.resolve import STATE_TENANT_KEY

API_PREFIX = "/api"
PUBLIC_PATHS = frozenset(
    {
        "/api/health",
        "/api/auth/status",
        "/api/auth/setup",
        "/api/auth/login",
        "/api/auth/join",
        # 私有化实例在线校验授权：调用方没有控制面账号，必须公开
        LICENSE_VERIFY_PATH,
    }
)


@dataclass(frozen=True)
class AccessDecision:
    error: str | None
    status_code: int = 401
    is_renewed: bool = False
    user: AuthUser | None = None


def is_protected_path(path: str) -> bool:
    is_api = path == API_PREFIX or path.startswith(f"{API_PREFIX}/")
    return is_api and path not in PUBLIC_PATHS


def decide_access(app: Any, slug: str, token: str | None) -> AccessDecision:
    """在控制库校验会话与成员关系；租户不存在时 404，不是成员时 403。"""
    with app.state.control_session_factory() as control:
        tenant = require_tenant_row(control, slug)
        if not is_password_set(control, tenant.id):
            return AccessDecision(error=MSG_NEED_SETUP)
        check = validate_session(control, token, tenant.id)
        control.commit()
    if not check.is_valid or check.user is None:
        return AccessDecision(
            error=check.denial or MSG_LOGIN_REQUIRED, status_code=check.status_code
        )
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
        if not scope["app"].state.settings.auth_enabled:
            await self.app(scope, receive, send)
            return
        conn = HTTPConnection(scope)
        token = read_session_token(conn)
        try:
            decision = await self._check(scope, conn, token)
        except AppError as error:
            await _error_response(error.message, error.status_code)(scope, receive, send)
            return
        if decision.error is not None or decision.user is None:
            message = decision.error or MSG_LOGIN_REQUIRED
            await _error_response(message, decision.status_code)(scope, receive, send)
            return
        if decision.is_renewed and token:
            cookie = session_cookie_header(token, is_secure_request(conn))
            send = _append_header(send, b"set-cookie", cookie)
        await self._call_as(decision.user, scope, receive, send)

    async def _check(self, scope: Scope, conn: HTTPConnection, token: str | None) -> AccessDecision:
        app = scope["app"]
        slug = await run_in_threadpool(session_tenant_slug, app, token)
        if slug:
            scope.setdefault("state", {})[STATE_TENANT_KEY] = slug
        tenant = await run_in_threadpool(tenant_for_connection, app, conn)
        return await run_in_threadpool(decide_access, app, tenant.slug, token)

    async def _call_as(self, user: AuthUser, scope: Scope, receive: Receive, send: Send) -> None:
        scope.setdefault("state", {})[STATE_USER_KEY] = user
        context_token = set_current_user(user.id)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_current_user(context_token)
