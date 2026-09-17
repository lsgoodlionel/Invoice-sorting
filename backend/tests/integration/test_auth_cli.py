"""reset-password 命令：admin 与 --user 两种用法、用户不存在时非 0 退出。"""

import pytest
from fastapi.testclient import TestClient

from invoice_sorting import main
from tests.auth_helpers import (
    MEMBER_PASSWORD,
    PASSWORD,
    auth_rows,
    create_user,
    logged_in_client,
    login,
)


@pytest.fixture
def data_env(auth_settings, monkeypatch):
    monkeypatch.setenv("INVOICE_SORTING_DATA_DIR", str(auth_settings.data_dir))


def test_reset_admin_keeps_member_sessions(auth_app, admin_client, data_env, capsys):
    created = create_user(admin_client, "member1")
    member = logged_in_client(auth_app, "member1")

    main.run(["reset-password"])

    assert "已清除 admin 登录密码" in capsys.readouterr().out
    assert [row.user_id for row in auth_rows(auth_app)] == [created["id"]]
    assert member.get("/api/expenses").json()["error"] == "请先设置初始密码"
    assert admin_client.post("/api/auth/setup", json={"password": PASSWORD}).status_code == 200
    assert member.get("/api/expenses").status_code == 200


def test_reset_named_user(auth_app, admin_client, data_env, capsys):
    created = create_user(admin_client, "member2")
    member = logged_in_client(auth_app, "member2")

    main.run(["reset-password", "--user", "Member2"])

    assert "已清除用户 member2 的密码" in capsys.readouterr().out
    assert member.get("/api/expenses").status_code == 401
    assert login(TestClient(auth_app), MEMBER_PASSWORD, "member2").status_code == 401
    assert admin_client.get("/api/expenses").status_code == 200
    users = admin_client.get("/api/users").json()["data"]
    target = next(user for user in users if user["id"] == created["id"])
    assert target["has_password"] is False
    url = f"/api/users/{created['id']}/password"
    assert admin_client.post(url, json={"password": "fresh-pass-123"}).status_code == 200
    assert login(TestClient(auth_app), "fresh-pass-123", "member2").status_code == 200


def test_reset_unknown_user_exits_nonzero(admin_client, data_env, capsys):
    with pytest.raises(SystemExit) as exited:
        main.run(["reset-password", "--user", "ghost"])

    assert exited.value.code == 1
    assert "用户不存在：ghost" in capsys.readouterr().err
    assert admin_client.get("/api/expenses").status_code == 200
