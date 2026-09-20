"""grant-platform-admin：首个平台管理员必须能离线开通（只读写本机控制库）。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from invoice_sorting.control.models import Account, Membership, Tenant
from invoice_sorting.control.repository import find_account
from invoice_sorting.main import create_app, run
from invoice_sorting.platform_admin.cli import PLATFORM_TENANT_SLUG, grant_platform_admin
from tests.conftest import make_saas_settings, make_settings
from tests.tenancy_helpers import add_member, login_at, open_tenants

PASSWORD = "ops-pass-12345"
USERNAME = "ops"


def control_rows(settings, model):
    from invoice_sorting.control.database import create_control_engine, make_control_session_factory

    engine = create_control_engine(settings)
    try:
        with make_control_session_factory(engine)() as control:
            return list(control.scalars(select(model)))
    finally:
        engine.dispose()


def test_creates_the_account_and_marks_it(tmp_path):
    settings = make_saas_settings(tmp_path)

    message = grant_platform_admin(settings, USERNAME, PASSWORD, "运营")

    accounts = control_rows(settings, Account)
    assert [account.username for account in accounts] == [USERNAME]
    assert accounts[0].is_platform_admin is True and accounts[0].display_name == "运营"
    assert "平台管理员" in message


def test_saas_account_gets_a_home_tenant_so_it_can_log_in(tmp_path):
    settings = make_saas_settings(tmp_path, auth_enabled=True)
    grant_platform_admin(settings, USERNAME, PASSWORD)

    tenants = control_rows(settings, Tenant)
    assert [tenant.slug for tenant in tenants] == [PLATFORM_TENANT_SLUG]
    assert [row.role for row in control_rows(settings, Membership)] == ["admin"]

    app = create_app(settings)
    client = TestClient(app)
    assert login_at(client, USERNAME, PASSWORD).status_code == 200
    assert client.get("/api/platform/overview").status_code == 200


def test_existing_member_keeps_its_own_tenant(tmp_path):
    settings = make_saas_settings(tmp_path, auth_enabled=True)
    app = create_app(settings)
    open_tenants(app, "alpha")
    add_member(app, "alpha", USERNAME, password=PASSWORD, role="member")

    grant_platform_admin(settings, USERNAME)

    assert {tenant.slug for tenant in control_rows(settings, Tenant)} == {"alpha"}
    assert [row.role for row in control_rows(settings, Membership)] == ["admin"]


def test_single_tenant_uses_the_default_tenant(tmp_path):
    settings = make_settings(tmp_path, auth_enabled=True)
    create_app(settings)  # 建库并写入 default 账套

    grant_platform_admin(settings, USERNAME, PASSWORD)

    assert {tenant.slug for tenant in control_rows(settings, Tenant)} == {"default"}


def test_password_can_be_reset_for_an_existing_account(tmp_path):
    settings = make_saas_settings(tmp_path, auth_enabled=True)
    grant_platform_admin(settings, USERNAME, PASSWORD)

    grant_platform_admin(settings, USERNAME, "another-pass-99")

    app = create_app(settings)
    assert login_at(TestClient(app), USERNAME, "another-pass-99").status_code == 200


def test_running_twice_is_idempotent(tmp_path):
    settings = make_saas_settings(tmp_path)
    grant_platform_admin(settings, USERNAME, PASSWORD)

    grant_platform_admin(settings, USERNAME)

    assert len(control_rows(settings, Account)) == 1
    assert len(control_rows(settings, Membership)) == 1


def test_new_account_without_password_is_rejected(tmp_path, monkeypatch):
    settings = make_saas_settings(tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    from invoice_sorting.common.errors import AppError

    with pytest.raises(AppError) as error:
        grant_platform_admin(settings, USERNAME)

    assert "初始密码" in error.value.message
    assert control_rows(settings, Account) == []


def test_short_password_is_rejected(tmp_path):
    from invoice_sorting.common.errors import AppError

    with pytest.raises(AppError):
        grant_platform_admin(make_saas_settings(tmp_path), USERNAME, "short")


def test_command_line_entry(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("INVOICE_SORTING_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("INVOICE_SORTING_DEPLOYMENT_MODE", "saas")

    run(["grant-platform-admin", "--username", USERNAME, "--password", PASSWORD])

    assert "平台管理员" in capsys.readouterr().out
    from invoice_sorting.config import Settings

    settings = Settings()
    with_account = find_account_in(settings, USERNAME)
    assert with_account is not None and with_account.is_platform_admin is True


def find_account_in(settings, username: str):
    from invoice_sorting.control.database import create_control_engine, make_control_session_factory

    engine = create_control_engine(settings)
    try:
        with make_control_session_factory(engine)() as control:
            return find_account(control, username)
    finally:
        engine.dispose()
