"""旧版单一密码库迁移为多用户：admin 沿用旧密码、旧会话失效、幂等。"""

import sqlite3

from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select

from invoice_sorting.auth.migrate import LEGACY_PASSWORD_KEY, migrate_users
from invoice_sorting.auth.passwords import hash_password
from invoice_sorting.db.models import AppSetting, AuthSession, User
from invoice_sorting.main import create_app
from tests.auth_helpers import COOKIE, PASSWORD, login
from tests.conftest import make_settings

OLD_TOKEN = "legacy-token"


def build_legacy_db(settings) -> None:
    settings.ensure_dirs()
    with sqlite3.connect(settings.db_path) as conn:
        conn.execute("CREATE TABLE app_setting (key VARCHAR(50) PRIMARY KEY, value TEXT)")
        conn.execute(
            "INSERT INTO app_setting VALUES (?, ?)", (LEGACY_PASSWORD_KEY, hash_password(PASSWORD))
        )
        conn.execute(
            "CREATE TABLE auth_session (token_hash VARCHAR(64) PRIMARY KEY, created_at DATETIME,"
            " last_seen_at DATETIME, expires_at DATETIME, user_agent VARCHAR(200))"
        )
        conn.execute(
            "INSERT INTO auth_session VALUES ('abc', '2026-09-01 10:00:00', '2026-09-01 10:00:00',"
            " '2099-01-01 00:00:00', 'old')"
        )


def test_legacy_password_becomes_admin_password(tmp_path):
    settings = make_settings(tmp_path, auth_enabled=True)
    build_legacy_db(settings)

    app = create_app(settings)

    with app.state.session_factory() as db:
        admin = db.scalar(select(User).where(User.username == "admin"))
        assert (admin.display_name, admin.role, admin.is_active) == ("管理员", "admin", True)
        assert db.get(AppSetting, LEGACY_PASSWORD_KEY) is None
        assert db.scalar(select(func.count()).select_from(AuthSession)) == 0
    columns = {c["name"]: c for c in inspect(app.state.engine).get_columns("auth_session")}
    assert columns["user_id"]["nullable"] is True
    with TestClient(app) as client:
        client.cookies.set(COOKIE, OLD_TOKEN)
        assert client.get("/api/expenses").json()["error"] == "请先登录"
        status = client.get("/api/auth/status").json()["data"]
        assert status["password_set"] is True and status["authenticated"] is False
        assert login(client).status_code == 200
        assert client.get("/api/expenses").status_code == 200


def test_migration_is_idempotent(tmp_path):
    settings = make_settings(tmp_path, auth_enabled=True)
    build_legacy_db(settings)
    create_app(settings)
    app = create_app(settings)
    with app.state.session_factory() as db:
        migrate_users(db)
        assert db.scalar(select(func.count(User.id))) == 1
        assert db.scalar(select(User.password_hash)) is not None
    with TestClient(app) as client:
        assert login(client).status_code == 200


def test_fresh_database_has_admin_without_password(auth_app, auth_client):
    with auth_app.state.session_factory() as db:
        users = list(db.scalars(select(User)))
    assert [(u.username, u.password_hash) for u in users] == [("admin", None)]
    assert auth_client.get("/api/auth/status").json()["data"]["password_set"] is False


def test_old_business_tables_get_nullable_actor_columns(tmp_path):
    settings = make_settings(tmp_path)
    settings.ensure_dirs()
    with sqlite3.connect(settings.db_path) as conn:
        conn.execute(
            "CREATE TABLE batch (id INTEGER PRIMARY KEY, name VARCHAR(100), status VARCHAR(20),"
            " created_at DATETIME)"
        )
        conn.execute("INSERT INTO batch (id, name, status) VALUES (1, '旧批次', 'draft')")
    app = create_app(settings)
    with TestClient(app) as client:
        batch = client.get("/api/batches/1").json()["data"]
    assert batch["name"] == "旧批次" and batch["created_by"] is None


def test_concurrent_admin_creation_is_ignored(auth_app, monkeypatch):
    from invoice_sorting.auth import migrate

    with auth_app.state.session_factory() as db:
        monkeypatch.setattr(migrate, "get_admin", lambda _db: None)
        migrate_users(db)  # admin 已存在，唯一约束冲突时静默回滚
        assert db.scalar(select(func.count(User.id))) == 1
