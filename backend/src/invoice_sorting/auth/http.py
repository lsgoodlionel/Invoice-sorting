"""HTTP 相关：客户端 IP、HTTPS 判断、会话 Cookie 读写。只信任本机反代的转发头。"""

import ipaddress

from starlette.requests import HTTPConnection
from starlette.responses import Response

COOKIE_NAME = "invoice_session"
SESSION_MAX_AGE = 30 * 24 * 60 * 60
TRUSTED_PROXIES = frozenset({"127.0.0.1", "::1"})
MAX_TOKEN_LENGTH = 128
UNKNOWN_CLIENT = "unknown"
USER_AGENT_HEADER = "user-agent"


def _valid_ip(value: str | None) -> str | None:
    candidate = (value or "").strip()
    try:
        return str(ipaddress.ip_address(candidate)) if candidate else None
    except ValueError:
        return None


def _is_from_local_proxy(conn: HTTPConnection) -> bool:
    return conn.client is not None and conn.client.host in TRUSTED_PROXIES


def client_ip(conn: HTTPConnection) -> str:
    if conn.client is None:
        return UNKNOWN_CLIENT
    if not _is_from_local_proxy(conn):
        return conn.client.host
    # X-Forwarded-For 取最后一个：Nginx $proxy_add_x_forwarded_for 把真实地址追加在末尾，
    # 前面的值可能是客户端自行伪造的
    forwarded_last = conn.headers.get("x-forwarded-for", "").split(",")[-1]
    return _valid_ip(conn.headers.get("x-real-ip")) or _valid_ip(forwarded_last) or conn.client.host


def is_secure_request(conn: HTTPConnection) -> bool:
    if conn.scope.get("scheme") == "https":
        return True
    proto = conn.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return _is_from_local_proxy(conn) and proto == "https"


def read_session_token(conn: HTTPConnection) -> str | None:
    token = conn.cookies.get(COOKIE_NAME, "")
    return token if 0 < len(token) <= MAX_TOKEN_LENGTH else None


def set_session_cookie(response: Response, token: str, secure: bool) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        path="/",
        secure=secure,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response, secure: bool) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", secure=secure, httponly=True, samesite="lax")


def session_cookie_header(token: str, secure: bool) -> bytes:
    """生成 Set-Cookie 头的值，供 ASGI 中间件续期时直接追加。"""
    holder = Response()
    set_session_cookie(holder, token, secure)
    return next(value for key, value in holder.raw_headers if key == b"set-cookie")
