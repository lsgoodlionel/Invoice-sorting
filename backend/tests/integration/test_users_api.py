"""用户管理接口：列表、创建、修改、重置密码及各项约束。"""

import pytest
from fastapi.testclient import TestClient

from tests.auth_helpers import (
    MEMBER_PASSWORD,
    PASSWORD,
    account_ids,
    create_user,
    logged_in_client,
    login,
)

USER_KEYS = {
    "id", "username", "display_name", "role", "is_active", "has_password", "created_at",
    "last_login_at",
}  # fmt: skip


def error(response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]


def test_list_and_create_users(admin_client):
    created = create_user(admin_client, "Qian", role="admin")

    assert set(created) == USER_KEYS
    assert (created["username"], created["display_name"], created["role"]) == (
        "qian",
        "qian",
        "admin",
    )
    assert created["is_active"] is True and created["has_password"] is True
    assert created["created_at"].endswith("+08:00") and created["last_login_at"] is None
    users = admin_client.get("/api/users").json()["data"]
    assert [u["username"] for u in users] == ["admin", "qian"]
    assert users[0]["last_login_at"] is not None


def test_duplicate_username_conflicts_case_insensitive(admin_client):
    create_user(admin_client, "wuu")
    body = {"username": "WUU", "password": MEMBER_PASSWORD, "role": "member"}
    assert error(admin_client.post("/api/users", json=body)) == (409, "用户名已存在")
    body = {"username": "ADMIN", "password": MEMBER_PASSWORD, "role": "member"}
    assert error(admin_client.post("/api/users", json=body)) == (409, "用户名已存在")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("username", "ab", "用户名需为 3–32 个字符"),
        ("username", "有中文的名字", "用户名需为 3–32 个字符"),
        ("username", "x" * 33, "用户名需为 3–32 个字符"),
        ("password", "short", "8–128"),
        ("password", "x" * 129, "8–128"),
        ("display_name", "  ", "姓名需为 1–32 个字符"),
        ("display_name", "名" * 33, "姓名需为 1–32 个字符"),
        ("role", "owner", "role"),
    ],
)
def test_create_user_validation(admin_client, field, value, message):
    body = {"username": "valid_user-1", "password": MEMBER_PASSWORD, "role": "member"}
    response = admin_client.post("/api/users", json={**body, field: value})
    assert response.status_code == 422
    assert message in response.json()["error"]


def test_update_display_name_and_role(auth_app, admin_client):
    created = create_user(admin_client, "zheng", display_name="郑")
    url = f"/api/users/{created['id']}"

    response = admin_client.patch(url, json={"display_name": " 郑某 ", "role": "admin"})

    data = response.json()["data"]
    assert (data["display_name"], data["role"]) == ("郑某", "admin")
    member = logged_in_client(auth_app, "zheng")
    assert member.get("/api/users").status_code == 200


def test_cannot_deactivate_or_demote_self(admin_client):
    assert error(admin_client.patch("/api/users/1", json={"is_active": False})) == (
        400,
        "不能停用自己",
    )
    assert error(admin_client.patch("/api/users/1", json={"role": "member"})) == (
        400,
        "不能把自己改为普通用户",
    )


def test_other_admin_can_demote_and_deactivate_admin(auth_app, admin_client):
    other = create_user(admin_client, "feng", role="admin")
    feng = logged_in_client(auth_app, "feng")
    url = f"/api/users/{other['id']}"
    assert feng.patch("/api/users/1", json={"role": "member"}).status_code == 200
    assert admin_client.get("/api/users").status_code == 403

    response = feng.patch("/api/users/1", json={"role": "admin", "is_active": False})
    assert response.status_code == 200
    assert feng.patch(url, json={"display_name": "冯"}).status_code == 200


def test_last_admin_rule_when_auth_disabled(client):
    last = "系统必须至少保留一名启用中且已设置密码的管理员"
    body = {"username": "chen", "password": MEMBER_PASSWORD, "role": "admin"}
    chen = client.post("/api/users", json=body).json()["data"]
    member = client.post("/api/users", json={**body, "username": "chu", "role": "member"})
    member_id = member.json()["data"]["id"]

    assert error(client.patch(f"/api/users/{chen['id']}", json={"is_active": False})) == (400, last)
    assert error(client.patch(f"/api/users/{chen['id']}", json={"role": "member"})) == (400, last)
    assert client.patch(f"/api/users/{member_id}", json={"is_active": False}).status_code == 200
    assert client.patch("/api/users/1", json={"display_name": "超管"}).status_code == 200


def test_update_and_reset_missing_user(admin_client):
    assert error(admin_client.patch("/api/users/999", json={"display_name": "x"})) == (
        404,
        "用户不存在",
    )
    body = {"password": MEMBER_PASSWORD}
    assert error(admin_client.post("/api/users/999/password", json=body)) == (404, "用户不存在")


def test_admin_reset_password_revokes_sessions(auth_app, admin_client):
    created = create_user(admin_client, "wei")
    member = logged_in_client(auth_app, "wei")
    url = f"/api/users/{created['id']}/password"

    assert admin_client.post(url, json={"password": "short"}).status_code == 422
    response = admin_client.post(url, json={"password": "reset-pass-789"})

    assert response.json() == {"ok": True, "data": None, "error": None}
    assert member.get("/api/expenses").status_code == 401
    assert account_ids(auth_app) == [1]
    assert login(TestClient(auth_app), MEMBER_PASSWORD, "wei").status_code == 401
    assert login(TestClient(auth_app), "reset-pass-789", "wei").status_code == 200


def test_reactivated_user_can_login_again(auth_app, admin_client):
    created = create_user(admin_client, "jiang")
    url = f"/api/users/{created['id']}"
    admin_client.patch(url, json={"is_active": False})
    assert login(TestClient(auth_app), MEMBER_PASSWORD, "jiang").status_code == 401
    assert admin_client.patch(url, json={"is_active": True}).json()["data"]["is_active"] is True
    assert login(TestClient(auth_app), MEMBER_PASSWORD, "jiang").status_code == 200


def test_concurrent_duplicate_create_maps_to_conflict(auth_app, admin_client, monkeypatch):
    from invoice_sorting.users import service

    monkeypatch.setattr(service, "find_account", lambda _db, _name: None)
    body = {"username": "admin", "password": PASSWORD, "role": "member"}
    assert error(admin_client.post("/api/users", json=body)) == (409, "用户名已存在")
