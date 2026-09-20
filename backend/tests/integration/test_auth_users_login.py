"""多用户登录：用户名密码、统一错误、计时一致、停用用户会话立即失效、修改本人密码。"""

from fastapi.testclient import TestClient

from invoice_sorting.auth import service
from invoice_sorting.control.models import Account
from tests.auth_helpers import (
    MEMBER_PASSWORD,
    PASSWORD,
    account_ids,
    create_user,
    logged_in_client,
    login,
)


def _deactivate_account(app, account_id: int) -> None:
    """直接在控制库停用账号（绕过接口，模拟平台侧操作）。"""
    with app.state.control_session_factory() as control:
        control.get(Account, account_id).is_active = False
        control.commit()


WRONG = {"ok": False, "data": None, "error": "用户名或密码错误"}


def test_member_login_returns_current_user(auth_app, admin_client):
    created = create_user(admin_client, "Zhang.San", display_name="张三")
    client = TestClient(auth_app)

    response = login(client, MEMBER_PASSWORD, "  ZHANG.san ")

    assert response.status_code == 200
    user = {"id": created["id"], "username": "zhang.san", "display_name": "张三", "role": "member"}
    assert response.json()["data"] == {"authenticated": True, "user": user}
    assert client.get("/api/auth/status").json()["data"]["user"] == user
    listed = next(u for u in admin_client.get("/api/users").json()["data"] if u["id"] == user["id"])
    assert listed["last_login_at"] is not None
    assert account_ids(auth_app) == [1, created["id"]]


def test_unknown_user_and_wrong_password_share_error(auth_app, admin_client, monkeypatch):
    create_user(admin_client, "lisi")
    checked: list[str | None] = []
    original = service.verify_password

    def spy(password, encoded):
        checked.append(encoded)
        return original(password, encoded)

    monkeypatch.setattr(service, "verify_password", spy)
    client = TestClient(auth_app)

    assert login(client, MEMBER_PASSWORD, "nobody").json() == WRONG
    assert login(client, "wrong-password", "lisi").json() == WRONG
    assert login(client, PASSWORD, "lisi").status_code == 401
    assert len(checked) == 3 and all(checked)


def test_user_without_password_cannot_login(auth_app, admin_client):
    created = create_user(admin_client, "wangwu")
    with auth_app.state.control_session_factory() as control:
        control.get(Account, created["id"]).password_hash = None
        control.commit()
    assert login(TestClient(auth_app), MEMBER_PASSWORD, "wangwu").json() == WRONG


def test_deactivated_user_cannot_login_and_sessions_end(auth_app, admin_client):
    created = create_user(admin_client, "zhaoliu")
    member = logged_in_client(auth_app, "zhaoliu")
    assert member.get("/api/expenses").status_code == 200

    response = admin_client.patch(f"/api/users/{created['id']}", json={"is_active": False})

    assert response.json()["data"]["is_active"] is False
    blocked = member.get("/api/expenses")
    assert (blocked.status_code, blocked.json()["error"]) == (401, "请先登录")
    assert member.get("/api/auth/status").json()["data"]["authenticated"] is False
    assert login(TestClient(auth_app), MEMBER_PASSWORD, "zhaoliu").json() == WRONG
    assert account_ids(auth_app) == [1]


def test_session_of_user_deactivated_directly_in_db_is_revoked(auth_app, admin_client):
    created = create_user(admin_client, "sunqi")
    member = logged_in_client(auth_app, "sunqi")
    other = logged_in_client(auth_app, "sunqi")
    _deactivate_account(auth_app, created["id"])

    assert member.get("/api/expenses").status_code == 401
    assert account_ids(auth_app) == [1]
    assert other.get("/api/expenses").status_code == 401


def test_member_changes_own_password_only(auth_app, admin_client):
    create_user(admin_client, "zhouba")
    member = logged_in_client(auth_app, "zhouba")
    second = logged_in_client(auth_app, "zhouba")
    body = {"current_password": MEMBER_PASSWORD, "new_password": "zhouba-new-pass"}

    assert member.post("/api/auth/password", json=body).status_code == 200

    assert member.get("/api/expenses").status_code == 200
    assert second.get("/api/expenses").status_code == 401
    assert admin_client.get("/api/expenses").status_code == 200
    assert login(TestClient(auth_app), "zhouba-new-pass", "zhouba").status_code == 200
    assert login(TestClient(auth_app), PASSWORD).status_code == 200


def test_change_password_when_auth_disabled(client):
    body = {"current_password": PASSWORD, "new_password": "another-pass-1"}
    response = client.post("/api/auth/password", json=body)
    assert response.status_code == 400
    assert response.json()["error"] == "未启用登录认证，无法修改密码"


def test_change_password_for_missing_user(auth_app, admin_client):
    from invoice_sorting.common.errors import NotFoundError

    with auth_app.state.control_session_factory() as control:
        try:
            service.change_password(control, 999, PASSWORD, "whatever-pass", None)
        except NotFoundError as exc:
            assert exc.message == "用户不存在"
        else:
            raise AssertionError("应抛出 NotFoundError")
