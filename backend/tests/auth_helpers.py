"""认证测试辅助：设置密码、登录、读取 Set-Cookie。"""

from datetime import timedelta

from sqlalchemy import select

from invoice_sorting.db.models import AuthSession, now

PASSWORD = "initial-pass-123"
COOKIE = "invoice_session"


def set_cookie_headers(response) -> list[str]:
    return response.headers.get_list("set-cookie")


def session_cookie_header(response) -> str:
    headers = [h for h in set_cookie_headers(response) if h.startswith(f"{COOKIE}=")]
    assert len(headers) == 1, headers
    return headers[0]


def setup_password(client, password: str = PASSWORD):
    response = client.post("/api/auth/setup", json={"password": password})
    assert response.status_code == 200, response.text
    return response


def auth_rows(app) -> list[AuthSession]:
    with app.state.session_factory() as db:
        return list(db.scalars(select(AuthSession)))


def shift_sessions(app, *, last_seen_ago: timedelta, expires_in: timedelta) -> None:
    with app.state.session_factory() as db:
        for row in db.scalars(select(AuthSession)):
            row.last_seen_at = now() - last_seen_ago
            row.expires_at = now() + expires_in
        db.commit()
