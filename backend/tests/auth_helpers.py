"""认证测试辅助：设置密码、登录、创建用户、读取 Set-Cookie。

会话统一存放在控制库，因此 auth_rows / shift_sessions 读写的是 control.db。
"""

from datetime import timedelta

from sqlalchemy import select

from invoice_sorting.control.models import ControlAuthSession
from invoice_sorting.db.models import now

PASSWORD = "initial-pass-123"
MEMBER_PASSWORD = "member-pass-123"
COOKIE = "invoice_session"
ADMIN = "admin"


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


def login(client, password: str = PASSWORD, username: str = ADMIN):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def create_user(
    admin_client,
    username: str,
    *,
    password: str = MEMBER_PASSWORD,
    role: str = "member",
    display_name: str | None = None,
) -> dict:
    body = {"username": username, "password": password, "role": role}
    if display_name is not None:
        body["display_name"] = display_name
    response = admin_client.post("/api/users", json=body)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def logged_in_client(app, username: str, password: str = MEMBER_PASSWORD):
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = login(client, password, username)
    assert response.status_code == 200, response.text
    return client


def auth_rows(app) -> list[ControlAuthSession]:
    with app.state.control_session_factory() as control:
        return list(control.scalars(select(ControlAuthSession)))


def account_ids(app) -> list[int]:
    return sorted(row.account_id for row in auth_rows(app))


def shift_sessions(app, *, last_seen_ago: timedelta, expires_in: timedelta) -> None:
    with app.state.control_session_factory() as control:
        for row in control.scalars(select(ControlAuthSession)):
            row.last_seen_at = now() - last_seen_ago
            row.expires_at = now() + expires_in
        control.commit()
