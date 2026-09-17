"""退出登录、修改密码、关闭认证开关、reset-password 命令。"""

from fastapi.testclient import TestClient

from invoice_sorting import main
from invoice_sorting.config import Settings
from tests.auth_helpers import (
    COOKIE,
    PASSWORD,
    auth_rows,
    login,
    set_cookie_headers,
    setup_password,
)

NEW_PASSWORD = "brand-new-pass-456"


def test_logout_invalidates_session(auth_app, auth_client):
    setup_password(auth_client)
    token = auth_client.cookies.get(COOKIE)
    response = auth_client.post("/api/auth/logout")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "data": None, "error": None}
    cleared = [h for h in set_cookie_headers(response) if h.startswith(f"{COOKIE}=")]
    assert cleared and "max-age=0" in cleared[0].lower()
    assert auth_rows(auth_app) == []
    auth_client.cookies.set(COOKIE, token)
    assert auth_client.get("/api/expenses").status_code == 401


def test_change_password_wrong_current(auth_client):
    setup_password(auth_client)
    body = {"current_password": "not-the-password", "new_password": NEW_PASSWORD}
    response = auth_client.post("/api/auth/password", json=body)
    assert response.status_code == 400
    assert response.json()["error"] == "当前密码错误"


def test_change_password_validates_new_length(auth_client):
    setup_password(auth_client)
    body = {"current_password": PASSWORD, "new_password": "short"}
    assert auth_client.post("/api/auth/password", json=body).status_code == 422


def test_change_password_requires_login(auth_client):
    setup_password(auth_client)
    auth_client.cookies.clear()
    body = {"current_password": PASSWORD, "new_password": NEW_PASSWORD}
    response = auth_client.post("/api/auth/password", json=body)
    assert response.status_code == 401
    assert response.json()["error"] == "请先登录"


def test_change_password_revokes_other_sessions(auth_app, auth_client):
    setup_password(auth_client)
    other = TestClient(auth_app)
    assert login(other).status_code == 200
    assert len(auth_rows(auth_app)) == 2

    body = {"current_password": PASSWORD, "new_password": NEW_PASSWORD}
    response = auth_client.post("/api/auth/password", json=body)
    assert response.status_code == 200
    assert response.json()["data"] is None

    assert auth_client.get("/api/expenses").status_code == 200
    assert other.get("/api/expenses").status_code == 401
    assert len(auth_rows(auth_app)) == 1
    anon = TestClient(auth_app)
    assert login(anon).status_code == 401
    assert login(anon, NEW_PASSWORD).status_code == 200


def test_auth_disabled_allows_everything(client):
    assert client.get("/api/expenses").status_code == 200
    assert client.get("/api/auth/status").json()["data"] == {
        "auth_enabled": False,
        "password_set": False,
        "authenticated": True,
        "user": None,
    }
    client.cookies.set(COOKIE, "forged")
    assert client.get("/api/settings").status_code == 200


def test_auth_enabled_env_switch(monkeypatch):
    monkeypatch.setenv("INVOICE_SORTING_AUTH_ENABLED", "false")
    assert Settings().auth_enabled is False
    monkeypatch.delenv("INVOICE_SORTING_AUTH_ENABLED")
    assert Settings().auth_enabled is True


def test_reset_password_command(auth_app, auth_client, auth_settings, monkeypatch, capsys):
    setup_password(auth_client)
    monkeypatch.setenv("INVOICE_SORTING_DATA_DIR", str(auth_settings.data_dir))

    main.run(["reset-password"])

    assert "已清除 admin 登录密码，请打开网页重新设置初始密码" in capsys.readouterr().out
    assert auth_rows(auth_app) == []
    status = auth_client.get("/api/auth/status").json()["data"]
    assert status == {
        "auth_enabled": True,
        "password_set": False,
        "authenticated": False,
        "user": None,
    }
    assert auth_client.get("/api/expenses").json()["error"] == "请先设置初始密码"
    assert auth_client.post("/api/auth/setup", json={"password": NEW_PASSWORD}).status_code == 200


def test_run_without_command_starts_server(tmp_path, monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setenv("INVOICE_SORTING_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("INVOICE_SORTING_OPEN_BROWSER", "false")
    monkeypatch.setenv("INVOICE_SORTING_WATCH_INBOX", "false")
    monkeypatch.setattr(main.uvicorn, "run", lambda app, host, port: calls.append((host, port)))
    main.run([])
    assert calls == [("127.0.0.1", 8765)]
