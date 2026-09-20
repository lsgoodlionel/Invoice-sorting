"""平台运营后台测试辅助：造平台管理员、已登录的平台客户端、常用请求体。"""

from typing import Any

from fastapi.testclient import TestClient

from invoice_sorting.control.repository import find_account
from invoice_sorting.main import create_app
from tests.conftest import make_saas_settings
from tests.tenancy_helpers import add_member, login_at, open_tenants

PLATFORM_ADMIN = "ops-admin"
PLATFORM_PASSWORD = "member-pass-123"


def mark_platform_admin(app: Any, username: str) -> None:
    with app.state.control_session_factory() as control:
        account = find_account(control, username)
        assert account is not None, username
        account.is_platform_admin = True
        control.commit()


def make_saas_app(tmp_path, **overrides):
    """多租户应用 + 两个账套（alpha/beta），各有一名账套管理员。"""
    app = create_app(make_saas_settings(tmp_path, auth_enabled=True, **overrides))
    open_tenants(app, "alpha", "beta")
    add_member(app, "alpha", "alpha-admin", role="admin")
    add_member(app, "beta", "beta-admin", role="admin")
    return app


def platform_app(tmp_path, **overrides):
    """再加一个只属于 platform 运营账套的平台管理员（模拟 CLI 开通的结果）。"""
    app = make_saas_app(tmp_path, **overrides)
    open_tenants(app, "platform")
    add_member(app, "platform", PLATFORM_ADMIN, role="admin", password=PLATFORM_PASSWORD)
    mark_platform_admin(app, PLATFORM_ADMIN)
    return app


def login_platform(app, username: str = PLATFORM_ADMIN) -> TestClient:
    """以平台管理员登录（裸域名，没有账套子域名）。"""
    client = TestClient(app)
    response = login_at(client, username, PLATFORM_PASSWORD)
    assert response.status_code == 200, response.text
    return client


def tenant_body(slug: str, **overrides) -> dict[str, Any]:
    body = {
        "slug": slug,
        "name": f"{slug} 账套",
        "admin_username": f"{slug}-boss",
        "admin_password": "member-pass-123",
    }
    return {**body, **overrides}
