"""登录、会话 Cookie 校验、续期，以及文件下载/上传受保护。"""

import io
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from invoice_sorting.attachments.storage import store_file
from invoice_sorting.common.constants import AttachmentKind
from tests.auth_helpers import (
    COOKIE,
    auth_rows,
    login,
    session_cookie_header,
    set_cookie_headers,
    setup_password,
    shift_sessions,
)


@pytest.fixture
def ready(auth_client):
    """已设置密码、但当前客户端未登录。"""
    setup_password(auth_client)
    auth_client.cookies.clear()
    return auth_client


def test_wrong_password_rejected(ready):
    response = login(ready, "wrong-password")
    assert response.status_code == 401
    assert response.json() == {"ok": False, "data": None, "error": "用户名或密码错误"}
    assert "set-cookie" not in response.headers
    assert ready.get("/api/expenses").json()["error"] == "请先登录"


def test_login_rejects_short_or_oversized_input(ready):
    assert login(ready, "short").status_code == 401
    assert login(ready, "x" * 2000).status_code == 422


def test_login_grants_access(ready):
    response = login(ready)
    assert response.status_code == 200
    user = {"id": 1, "username": "admin", "display_name": "管理员", "role": "admin"}
    assert response.json()["data"] == {"authenticated": True, "user": user}
    session_cookie_header(response)
    assert ready.get("/api/expenses").status_code == 200
    assert ready.get("/api/auth/status").json()["data"]["authenticated"] is True


def test_attachment_download_and_upload_protected(auth_app, auth_settings, ready, tmp_path):
    png_path = tmp_path / "订单.png"
    buffer = io.BytesIO()
    Image.new("RGB", (40, 40), "red").save(buffer, format="PNG")
    png_path.write_bytes(buffer.getvalue())
    with auth_app.state.session_factory() as db:
        attachment = store_file(db, auth_settings, png_path, "订单.png", AttachmentKind.ORDER)
        db.commit()
        url = f"/api/attachments/{attachment.id}/file"
    upload = {"files": ("订单.png", buffer.getvalue(), "image/png")}

    assert ready.get(url).status_code == 401
    assert ready.post("/api/imports", files=upload).status_code == 401

    login(ready)
    response = ready.get(url)
    assert response.status_code == 200
    assert response.content == buffer.getvalue()
    assert ready.post("/api/imports", files=upload).status_code == 200


@pytest.mark.parametrize("value", ["forged-token", "", "x" * 5000])
def test_forged_cookie_is_rejected(ready, value):
    login(ready)
    ready.cookies.clear()
    ready.cookies.set(COOKIE, value)
    response = ready.get("/api/expenses")
    assert response.status_code == 401
    assert response.json()["error"] == "请先登录"
    assert ready.get("/api/auth/status").json()["data"]["authenticated"] is False


def test_expired_session_is_rejected(auth_app, ready):
    login(ready)
    shift_sessions(auth_app, last_seen_ago=timedelta(days=31), expires_in=timedelta(seconds=-1))
    assert ready.get("/api/expenses").status_code == 401


def test_expired_sessions_purged_on_login(auth_app, ready):
    login(ready)
    shift_sessions(auth_app, last_seen_ago=timedelta(days=31), expires_in=timedelta(days=-1))
    login(ready)
    assert len(auth_rows(auth_app)) == 1


def test_recent_session_is_not_rewritten(auth_app, ready):
    login(ready)
    before = max(auth_rows(auth_app), key=lambda item: item.created_at)
    response = ready.get("/api/expenses")
    assert response.status_code == 200
    assert set_cookie_headers(response) == []
    after = next(row for row in auth_rows(auth_app) if row.token_hash == before.token_hash)
    assert after.last_seen_at == before.last_seen_at
    assert after.expires_at == before.expires_at


def test_stale_session_is_renewed(auth_app, ready):
    login(ready)
    shift_sessions(auth_app, last_seen_ago=timedelta(hours=2), expires_in=timedelta(days=1))
    response = ready.get("/api/expenses")
    assert response.status_code == 200
    parts = [p.strip().lower() for p in session_cookie_header(response).split(";")]
    assert "max-age=2592000" in parts and "httponly" in parts
    row = max(auth_rows(auth_app), key=lambda item: item.last_seen_at)
    lifetime = row.expires_at - row.last_seen_at
    assert timedelta(days=29, hours=23) < lifetime <= timedelta(days=30)
    assert ready.get("/api/expenses").status_code == 200


def test_session_valid_across_clients(auth_app, ready):
    token = session_cookie_header(login(ready)).split(";")[0].split("=", 1)[1]
    other = TestClient(auth_app)
    assert other.get("/api/expenses").status_code == 401
    other.cookies.set(COOKIE, token)
    assert other.get("/api/expenses").status_code == 200


def test_status_renews_stale_session(auth_app, ready):
    login(ready)
    shift_sessions(auth_app, last_seen_ago=timedelta(hours=2), expires_in=timedelta(days=1))
    response = ready.get("/api/auth/status")
    assert response.json()["data"]["authenticated"] is True
    session_cookie_header(response)
