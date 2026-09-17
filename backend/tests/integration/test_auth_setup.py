"""未设置密码时的访问控制与首次设置初始密码。"""

import threading

import pytest
from fastapi.testclient import TestClient

from invoice_sorting.main import create_app
from tests.auth_helpers import PASSWORD, auth_rows, session_cookie_header, setup_password
from tests.conftest import make_settings


def test_status_before_setup(auth_client):
    response = auth_client.get("/api/auth/status")
    assert response.status_code == 200
    assert response.json()["data"] == {
        "auth_enabled": True,
        "password_set": False,
        "authenticated": False,
    }


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", "/api/expenses"), ("get", "/api/settings"), ("post", "/api/auth/logout")],
)
def test_protected_endpoints_require_setup(auth_client, method, path):
    response = getattr(auth_client, method)(path)
    assert response.status_code == 401
    assert response.json() == {"ok": False, "data": None, "error": "请先设置初始密码"}


def test_login_before_setup_conflicts(auth_client):
    response = auth_client.post("/api/auth/login", json={"password": PASSWORD})
    assert response.status_code == 409
    assert response.json()["error"] == "请先设置初始密码"


def test_health_and_frontend_are_public(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    app = create_app(make_settings(tmp_path, auth_enabled=True, frontend_dist=dist))
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/").text == "<html>app</html>"
        assert client.get("/expenses/12").text == "<html>app</html>"
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/api/expenses").status_code == 401


@pytest.mark.parametrize("password", ["short", "1234567", "x" * 129])
def test_setup_rejects_invalid_length(auth_client, password):
    response = auth_client.post("/api/auth/setup", json={"password": password})
    assert response.status_code == 422
    assert "8–128" in response.json()["error"]
    assert auth_client.get("/api/auth/status").json()["data"]["password_set"] is False


def test_setup_rejects_non_string(auth_client):
    response = auth_client.post("/api/auth/setup", json={"password": 12345678})
    assert response.status_code == 422


def test_setup_accepts_boundary_lengths(auth_client, tmp_path):
    assert auth_client.post("/api/auth/setup", json={"password": "x" * 128}).status_code == 200
    other = TestClient(create_app(make_settings(tmp_path / "b", auth_enabled=True)))
    assert other.post("/api/auth/setup", json={"password": "12345678"}).status_code == 200


def test_setup_sets_session_cookie(auth_app, auth_client):
    response = setup_password(auth_client)
    assert response.json() == {"ok": True, "data": {"authenticated": True}, "error": None}
    header = session_cookie_header(response)
    parts = [part.strip().lower() for part in header.split(";")]
    assert "httponly" in parts
    assert "samesite=lax" in parts
    assert "path=/" in parts
    assert "max-age=2592000" in parts
    assert "secure" not in parts
    token = header.split(";")[0].split("=", 1)[1]
    rows = auth_rows(auth_app)
    assert len(rows) == 1
    assert rows[0].token_hash != token and len(rows[0].token_hash) == 64
    assert auth_client.get("/api/auth/status").json()["data"] == {
        "auth_enabled": True,
        "password_set": True,
        "authenticated": True,
    }
    assert auth_client.get("/api/expenses").status_code == 200


def test_setup_cookie_secure_behind_local_https_proxy(auth_app):
    client = TestClient(auth_app, client=("127.0.0.1", 50000))
    response = client.post(
        "/api/auth/setup", json={"password": PASSWORD}, headers={"X-Forwarded-Proto": "https"}
    )
    assert response.status_code == 200
    parts = [p.strip().lower() for p in session_cookie_header(response).split(";")]
    assert "secure" in parts


def test_forwarded_proto_ignored_from_remote_client(auth_app):
    client = TestClient(auth_app, client=("203.0.113.9", 50000))
    response = client.post(
        "/api/auth/setup", json={"password": PASSWORD}, headers={"X-Forwarded-Proto": "https"}
    )
    parts = [p.strip().lower() for p in session_cookie_header(response).split(";")]
    assert "secure" not in parts


def test_second_setup_conflicts(auth_client):
    setup_password(auth_client)
    auth_client.cookies.clear()
    response = auth_client.post("/api/auth/setup", json={"password": "another-pass-1"})
    assert response.status_code == 409
    assert response.json()["error"] == "已设置过初始密码，请直接登录"
    assert "set-cookie" not in response.headers
    assert auth_client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 200


def test_concurrent_setup_only_one_succeeds(auth_app):
    barrier = threading.Barrier(4)
    results: list[int] = []

    def attempt(index: int) -> None:
        client = TestClient(auth_app)
        barrier.wait()
        response = client.post("/api/auth/setup", json={"password": f"password-{index}"})
        results.append(response.status_code)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == [200, 409, 409, 409]
    assert len(auth_rows(auth_app)) == 1


def test_setup_conflict_from_other_process_maps_to_409(auth_app, auth_client, monkeypatch):
    from invoice_sorting.auth import service
    from invoice_sorting.db.models import AppSetting

    def racing_store(db, encoded):
        with auth_app.state.session_factory() as other:
            other.add(AppSetting(key=service.PASSWORD_KEY, value="scrypt$other"))
            other.commit()
        db.add(AppSetting(key=service.PASSWORD_KEY, value=encoded))
        db.flush()

    monkeypatch.setattr(service, "_store_hash", racing_store)
    response = auth_client.post("/api/auth/setup", json={"password": PASSWORD})
    assert response.status_code == 409
    assert response.json()["error"] == "已设置过初始密码，请直接登录"
