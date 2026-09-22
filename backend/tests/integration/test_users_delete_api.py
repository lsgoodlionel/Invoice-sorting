"""删除用户（DELETE /api/users/{id}）：不能登录、列表消失、同名可重建、历史仍显示原姓名。

测试数据全部虚构：账号名、姓名与密码都是编造的，不对应任何真实人员。
"""

from fastapi.testclient import TestClient

from invoice_sorting.licensing.guard import WriteBlock, register_write_guard
from invoice_sorting.main import create_app
from tests.accounts_helpers import can_login, find_account, mirror_user
from tests.auth_helpers import MEMBER_PASSWORD, PASSWORD, create_user, logged_in_client

EXPENSE = {"spent_on": "2026-09-15", "amount_cents": 1200, "merchant": "虚构便利店"}
READONLY = "系统只读，暂不能修改"


def error(response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]


def usernames(client) -> list[str]:
    return [user["username"] for user in client.get("/api/users").json()["data"]]


def ref(user_id: int, display_name: str) -> dict:
    return {"id": user_id, "display_name": display_name}


def test_deleted_user_cannot_login_and_leaves_the_list(auth_app, admin_client):
    carol = create_user(admin_client, "carol", display_name="虚构丙")
    carol_client = logged_in_client(auth_app, "carol")

    response = admin_client.delete(f"/api/users/{carol['id']}")

    assert response.status_code == 200, response.text
    assert response.json()["data"] == {
        "id": carol["id"],
        "username": "carol",
        "is_account_removed": True,
    }
    assert usernames(admin_client) == ["admin"]
    assert not can_login(auth_app, "carol", MEMBER_PASSWORD)
    assert carol_client.get("/api/expenses").status_code == 401
    mirror = mirror_user(auth_app, carol["id"])
    assert mirror.is_deleted and mirror.display_name == "虚构丙"


def test_same_username_can_be_reused_while_history_keeps_original_name(auth_app, admin_client):
    old = create_user(admin_client, "carol", display_name="虚构丙")
    carol_client = logged_in_client(auth_app, "carol")
    expense_id = carol_client.post("/api/expenses", json=EXPENSE).json()["data"]["id"]
    admin_client.delete(f"/api/users/{old['id']}")

    new = create_user(admin_client, "carol", password="another-pass-9", display_name="虚构丁")

    assert new["id"] != old["id"]  # 最后创建的账号被删后，id 也不复用
    assert can_login(auth_app, "carol", "another-pass-9")
    assert usernames(admin_client) == ["admin", "carol"]
    detail = admin_client.get(f"/api/expenses/{expense_id}").json()["data"]
    assert detail["created_by"] == ref(old["id"], "虚构丙")
    assert {event["actor"]["display_name"] for event in detail["timeline"]} == {"虚构丙"}
    assert mirror_user(auth_app, old["id"]).username.startswith("carol~")
    assert mirror_user(auth_app, new["id"]).username == "carol"


def test_cannot_delete_self_or_missing_user(admin_client):
    assert error(admin_client.delete("/api/users/1")) == (400, "不能删除自己的账号")
    assert error(admin_client.delete("/api/users/999")) == (404, "用户不存在")


def test_last_usable_admin_cannot_be_deleted(client):
    body = {"username": "chen", "password": MEMBER_PASSWORD, "role": "admin"}
    chen = client.post("/api/users", json=body).json()["data"]
    assert client.delete("/api/users/1").status_code == 200

    response = client.delete(f"/api/users/{chen['id']}")

    assert error(response) == (409, "不能删除账套里最后一名可用的管理员")
    assert usernames(client) == ["chen"]


def test_member_cannot_delete_users(auth_app, admin_client):
    create_user(admin_client, "dora")
    target = create_user(admin_client, "eric")
    dora = logged_in_client(auth_app, "dora")

    assert dora.delete(f"/api/users/{target['id']}").status_code == 403
    assert "eric" in usernames(admin_client)


def test_delete_is_blocked_when_read_only(auth_app, admin_client):
    target = create_user(admin_client, "fay")
    register_write_guard(auth_app, lambda conn: WriteBlock(code="readonly", message=READONLY))

    assert error(admin_client.delete(f"/api/users/{target['id']}")) == (403, READONLY)
    assert find_account(auth_app, "fay") is not None


def test_deleted_builtin_admin_is_not_recreated_on_restart(auth_settings, auth_app, admin_client):
    create_user(admin_client, "gina", password=MEMBER_PASSWORD, role="admin")
    gina = logged_in_client(auth_app, "gina")
    assert gina.delete("/api/users/1").status_code == 200

    restarted = create_app(auth_settings)

    with TestClient(restarted) as fresh:
        status = fresh.get("/api/auth/status").json()["data"]
    assert status["password_set"] is True
    assert find_account(restarted, "admin") is None
    assert not can_login(restarted, "admin", PASSWORD)
    assert can_login(restarted, "gina", MEMBER_PASSWORD)
