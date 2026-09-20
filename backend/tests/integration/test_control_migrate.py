"""升级迁移：业务库 app_user 搬到控制库 account + membership（id 不变），会话一并搬迁。"""

from datetime import timedelta

import pytest
from sqlalchemy import func, select

from invoice_sorting.control.models import Account, ControlAuthSession, Membership, Tenant
from invoice_sorting.db.models import AuthSession, User, now
from invoice_sorting.db.session import create_db_engine, init_db, make_session_factory
from invoice_sorting.main import create_app
from tests.conftest import make_settings

LEGACY_TOKEN = "a" * 64


def _seed_legacy_business_db(settings, token_hash: str = LEGACY_TOKEN) -> None:
    """模拟老部署：只有业务库，账号与会话都在其中。"""
    settings.ensure_dirs()
    engine = create_db_engine(f"sqlite:///{settings.db_path}")
    try:
        init_db(engine)
        current = now()
        with make_session_factory(engine)() as db:
            db.add(
                User(
                    id=1,
                    username="admin",
                    display_name="管理员",
                    role="admin",
                    password_hash="hash-admin",
                    is_active=True,
                    created_at=current,
                )
            )
            db.add(
                User(
                    id=7,
                    username="zhangsan",
                    display_name="张三",
                    role="member",
                    password_hash="hash-zhangsan",
                    is_active=False,
                    created_at=current,
                )
            )
            db.flush()
            db.add(
                AuthSession(
                    token_hash=token_hash,
                    user_id=1,
                    created_at=current,
                    last_seen_at=current,
                    expires_at=current + timedelta(days=30),
                )
            )
            db.commit()
    finally:
        engine.dispose()


@pytest.fixture
def upgraded(tmp_path):
    settings = make_settings(tmp_path)
    _seed_legacy_business_db(settings)
    app = create_app(settings)
    yield app, settings


def _control_rows(app, model) -> list:
    with app.state.control_session_factory() as control:
        return list(control.scalars(select(model)))


def test_accounts_keep_their_business_ids(upgraded):
    app, _ = upgraded

    accounts = {row.id: row for row in _control_rows(app, Account)}

    assert set(accounts) == {1, 7}
    assert accounts[1].username == "admin"
    assert accounts[1].password_hash == "hash-admin"
    assert accounts[7].display_name == "张三"
    assert accounts[7].is_active is False


def test_memberships_point_to_default_tenant(upgraded):
    app, _ = upgraded

    tenants = _control_rows(app, Tenant)
    memberships = {row.account_id: row for row in _control_rows(app, Membership)}

    assert [tenant.slug for tenant in tenants] == ["default"]
    assert set(memberships) == {1, 7}
    assert memberships[1].role == "admin"
    assert memberships[7].role == "member"
    assert memberships[7].is_active is False
    assert all(row.tenant_id == tenants[0].id for row in memberships.values())


def test_sessions_are_copied_to_control_db(upgraded):
    app, _ = upgraded

    sessions = _control_rows(app, ControlAuthSession)

    assert [row.token_hash for row in sessions] == [LEGACY_TOKEN]
    assert sessions[0].account_id == 1
    assert sessions[0].tenant_id is not None


def test_business_user_table_is_kept_as_mirror(upgraded):
    app, _ = upgraded

    with app.state.session_factory() as db:
        admin = db.get(User, 1)

    assert admin is not None
    assert admin.password_hash == "hash-admin"  # 本批不删列，回滚旧版本仍可登录


def test_migration_is_idempotent(upgraded):
    _, settings = upgraded

    second = create_app(settings)

    with second.state.control_session_factory() as control:
        assert control.scalar(select(func.count(Account.id))) == 2
        assert control.scalar(select(func.count(Membership.id))) == 2
        assert control.scalar(select(func.count(ControlAuthSession.token_hash))) == 1
        assert control.scalar(select(func.count(Tenant.id))) == 1


def test_existing_sessions_keep_working_after_upgrade(tmp_path):
    """老部署升级后不需要重新登录：会话已随批次一搬到控制库，密码哈希原样保留。"""
    from fastapi.testclient import TestClient

    from invoice_sorting.auth.passwords import hash_password
    from invoice_sorting.auth.sessions import hash_token
    from invoice_sorting.control.models import Account
    from tests.auth_helpers import COOKIE

    settings = make_settings(tmp_path, auth_enabled=True)
    _seed_legacy_business_db(settings, token_hash=hash_token("old-token"))
    with make_session_factory(create_db_engine(f"sqlite:///{settings.db_path}"))() as db:
        db.get(User, 1).password_hash = hash_password("old-pass-123")
        db.commit()

    app = create_app(settings)

    with app.state.control_session_factory() as control:
        assert control.get(Account, 1).password_hash is not None
    with TestClient(app) as client:
        client.cookies.set(COOKIE, "old-token")
        assert client.get("/api/expenses").status_code == 200
        assert client.get("/api/auth/status").json()["data"]["user"]["username"] == "admin"
