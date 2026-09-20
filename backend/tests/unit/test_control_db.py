"""控制库：建表、轻量迁移幂等、租户与账号仓储。"""

import sqlite3

import pytest
from sqlalchemy import inspect

from invoice_sorting.common.errors import AppError
from invoice_sorting.config import Settings
from invoice_sorting.control.database import (
    create_control_engine,
    init_control_db,
    make_control_session_factory,
)
from invoice_sorting.control.repository import (
    create_account,
    create_tenant,
    ensure_membership,
    ensure_tenant,
    find_account,
    find_membership,
    find_tenant,
    list_tenants,
    normalize_slug,
)

CONTROL_TABLES = {
    "tenant",
    "plan",
    "account",
    "membership",
    "auth_session",
    "invite",
    "usage_snapshot",
    "license_record",
}


@pytest.fixture
def control(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    engine = create_control_engine(settings)
    init_control_db(engine)
    factory = make_control_session_factory(engine)
    try:
        with factory() as db:
            yield db
    finally:
        engine.dispose()


def test_control_db_creates_all_tables(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    engine = create_control_engine(settings)
    try:
        init_control_db(engine)

        assert CONTROL_TABLES <= set(inspect(engine).get_table_names())
        assert settings.control_db_path.exists()
    finally:
        engine.dispose()


def test_init_control_db_is_idempotent(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    engine = create_control_engine(settings)
    try:
        init_control_db(engine)
        init_control_db(engine)
        init_control_db(engine)

        assert CONTROL_TABLES <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_init_control_db_adds_missing_columns_to_existing_tables(tmp_path):
    """老版本控制库升级时补齐新增列，已有数据保留。"""
    settings = Settings(data_dir=tmp_path / "data")
    settings.data_dir.mkdir(parents=True)
    with sqlite3.connect(settings.control_db_path) as conn:
        conn.execute("CREATE TABLE tenant (id INTEGER PRIMARY KEY, slug VARCHAR(50))")
        conn.execute("INSERT INTO tenant VALUES (1, 'alpha')")
    engine = create_control_engine(settings)
    try:
        init_control_db(engine)

        columns = {column["name"] for column in inspect(engine).get_columns("tenant")}
        assert {"name", "status", "plan_id", "expires_on", "data_dirname"} <= columns
        with engine.connect() as conn:
            row = conn.exec_driver_sql("SELECT slug, status FROM tenant").one()
        assert tuple(row) == ("alpha", "active")
    finally:
        engine.dispose()


def test_control_db_does_not_contain_business_tables(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    engine = create_control_engine(settings)
    try:
        init_control_db(engine)

        assert "expense" not in set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(" Alpha ", "alpha"), ("BETA", "beta"), ("", "")],
)
def test_normalize_slug(raw, expected):
    assert normalize_slug(raw) == expected


def test_create_and_find_tenant(control):
    created = create_tenant(control, "Alpha", "阿尔法")
    control.flush()

    assert created.slug == "alpha"
    assert created.status == "active"
    assert find_tenant(control, "ALPHA") is created
    assert find_tenant(control, "unknown") is None


def test_create_tenant_rejects_duplicate_slug(control):
    create_tenant(control, "alpha", "阿尔法")
    control.flush()

    with pytest.raises(AppError) as excinfo:
        create_tenant(control, "Alpha", "另一个")

    assert excinfo.value.status_code == 409


def test_create_tenant_rejects_invalid_slug(control):
    with pytest.raises(AppError) as excinfo:
        create_tenant(control, "有中文", "名字")

    assert excinfo.value.status_code == 400


def test_ensure_tenant_is_idempotent(control):
    first = ensure_tenant(control, "default", "默认账套")
    control.flush()
    second = ensure_tenant(control, "default", "别的名字")

    assert first.id == second.id
    assert first.name == "默认账套"  # 已存在时不覆盖名称
    assert len(list_tenants(control)) == 1


def test_create_account_normalizes_username(control):
    account = create_account(control, " Admin ", "管理员", password_hash="x")
    control.flush()

    assert account.username == "admin"
    assert account.is_platform_admin is False
    assert find_account(control, "ADMIN") is account


def test_create_account_rejects_duplicate_username(control):
    create_account(control, "admin", "管理员")
    control.flush()

    with pytest.raises(AppError) as excinfo:
        create_account(control, "Admin", "重复")

    assert excinfo.value.status_code == 409


def test_ensure_membership_is_idempotent(control):
    tenant = create_tenant(control, "alpha", "阿尔法")
    account = create_account(control, "admin", "管理员")
    control.flush()

    first = ensure_membership(control, account.id, tenant.id, "admin")
    control.flush()
    second = ensure_membership(control, account.id, tenant.id, "member")

    assert first.id == second.id
    assert first.role == "admin"  # 已存在时不降级
    assert find_membership(control, account.id, tenant.id) is first
