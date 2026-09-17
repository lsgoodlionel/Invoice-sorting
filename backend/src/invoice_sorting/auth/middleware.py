"""认证中间件（纯 ASGI）：保护 /api/*（公开白名单除外），会话续期时追加 Set-Cookie。

非 /api 路径（前端静态文件、SPA 回退）不拦截；settings.auth_enabled=False 时全部放行。
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker
from starlette.concurrency import run_in_threadpool
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from invoice_sorting.auth.http import is_secure_request, read_session_token, session_cookie_header
from invoice_sorting.auth.service import MSG_LOGIN_REQUIRED, MSG_NEED_SETUP, is_password_set
from invoice_sorting.auth.sessions import validate_session

API_PREFIX = "/api"
PUBLIC_PATHS = frozenset({"/api/health", "/api/auth/status", "/api/auth/setup", "/api/auth/login"})


@dataclass(frozen=True)
class AccessDecision:
    error: str | None
    is_renewed: bool = False


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
    return AccessDecision(error=None, is_renewed=check.is_renewed)


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
        token = read_session_token(conn)
        decision = await run_in_threadpool(decide_access, state.session_factory, token)
        if decision.error is not None:
            body = {"ok": False, "data": None, "error": decision.error}
            await JSONResponse(body, status_code=401)(scope, receive, send)
            return
        if decision.is_renewed and token:
            cookie = session_cookie_header(token, is_secure_request(conn))
            send = _append_header(send, b"set-cookie", cookie)
        await self.app(scope, receive, send)
