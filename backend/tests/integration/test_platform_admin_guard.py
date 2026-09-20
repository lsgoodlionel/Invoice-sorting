"""平台接口只允许平台管理员：租户管理员不能导出别的账套的数据。"""

import pytest
from fastapi.testclient import TestClient

from invoice_sorting.control.repository import find_account
from invoice_sorting.main import create_app
from tests.conftest import make_saas_settings, make_settings
from tests.tenancy_helpers import add_member, login_at, open_tenants

EXPORT_PATH = "/api/platform/tenants/{slug}/export"


@pytest.fixture
def two_tenants(tmp_path):
    app = create_app(make_saas_settings(tmp_path, auth_enabled=True))
    open_tenants(app, "alpha", "beta")
    add_member(app, "alpha", "alpha-admin", role="admin")
    add_member(app, "beta", "beta-admin", role="admin")
    return app


def make_platform_admin(app, username: str) -> None:
    with app.state.control_session_factory() as control:
        account = find_account(control, username)
        assert account is not None
        account.is_platform_admin = True
        control.commit()


def test_tenant_admin_cannot_export_other_tenant(two_tenants):
    client = TestClient(two_tenants)
    assert login_at(client, "alpha-admin").status_code == 200

    response = client.post(EXPORT_PATH.format(slug="beta"))

    assert response.status_code == 403, response.text
    assert "平台管理员" in response.json()["error"]


def test_tenant_admin_cannot_export_own_tenant_through_platform_path(two_tenants):
    client = TestClient(two_tenants)
    login_at(client, "alpha-admin")

    assert client.post(EXPORT_PATH.format(slug="alpha")).status_code == 403


def test_platform_admin_can_export_any_tenant(two_tenants):
    make_platform_admin(two_tenants, "alpha-admin")
    client = TestClient(two_tenants)
    login_at(client, "alpha-admin")

    response = client.post(EXPORT_PATH.format(slug="beta"))

    assert response.status_code == 200, response.text
    assert response.json()["data"]["slug"] == "beta"


def test_single_tenant_admin_keeps_platform_access(tmp_path):
    """单账套部署没有平台概念：管理员照常可用平台路径导出自己的数据。"""
    from tests.auth_helpers import setup_password

    app = create_app(make_settings(tmp_path, auth_enabled=True))
    client = TestClient(app)
    setup_password(client)

    assert client.post(EXPORT_PATH.format(slug="default")).status_code == 200
