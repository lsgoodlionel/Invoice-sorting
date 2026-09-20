"""多租户认证：按账号归属定位账套、子域名越权 403、账套切换。

单租户部署不暴露任何账套能力（接口 404、状态里没有账套字段）。
"""

import pytest
from fastapi.testclient import TestClient

from invoice_sorting.main import create_app
from tests.conftest import make_saas_settings
from tests.tenancy_helpers import add_member, host_headers, login_at, open_tenants

EXPENSE = {"spent_on": "2026-09-15", "amount_cents": 1200, "merchant": "阿尔法便利店"}
PASSWORD = "member-pass-123"


@pytest.fixture
def saas_auth_app(tmp_path):
    """开启登录认证的多租户部署，配置了 tenant_host_suffix=example.com。"""
    return create_app(make_saas_settings(tmp_path, auth_enabled=True))


@pytest.fixture
def two_tenants(saas_auth_app):
    open_tenants(saas_auth_app, "alpha", "beta")
    return saas_auth_app


def _client(app) -> TestClient:
    return TestClient(app)


def test_login_without_subdomain_enters_the_only_tenant(two_tenants):
    add_member(two_tenants, "alpha", "zhangsan")
    client = _client(two_tenants)

    response = login_at(client, "zhangsan")

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["user"]["username"] == "zhangsan"
    assert data["tenant"] == {"slug": "alpha", "name": "alpha 账套"}
    assert client.get("/api/expenses").status_code == 200


def test_login_on_foreign_subdomain_is_forbidden(two_tenants):
    add_member(two_tenants, "alpha", "zhangsan")

    response = login_at(_client(two_tenants), "zhangsan", slug="beta")

    assert response.status_code == 403
    assert response.json()["error"] == "当前账号不属于该账套，请联系管理员开通"


def test_account_without_any_tenant_cannot_login(two_tenants):
    add_member(two_tenants, "alpha", "zhangsan")
    with two_tenants.state.control_session_factory() as control:
        from invoice_sorting.control.models import Membership

        control.query(Membership).delete()
        control.commit()

    response = login_at(_client(two_tenants), "zhangsan")

    assert response.status_code == 403
    assert "尚未加入任何账套" in response.json()["error"]


def test_session_of_one_tenant_cannot_use_another_subdomain(two_tenants):
    add_member(two_tenants, "alpha", "zhangsan")
    add_member(two_tenants, "beta", "lisi")
    client = _client(two_tenants)
    assert login_at(client, "zhangsan").status_code == 200

    response = client.get("/api/expenses", headers=host_headers("beta"))

    assert response.status_code == 403
    assert response.json()["error"] == "当前账号不属于该账套，请联系管理员开通"


def test_subdomain_login_pins_that_tenant(two_tenants):
    add_member(two_tenants, "alpha", "zhangsan")
    add_member(two_tenants, "beta", "zhangsan")
    client = _client(two_tenants)

    response = login_at(client, "zhangsan", slug="beta")

    assert response.json()["data"]["tenant"]["slug"] == "beta"
    assert client.get("/api/expenses").status_code == 200


def test_tenants_endpoint_lists_account_tenants(two_tenants):
    add_member(two_tenants, "alpha", "zhangsan")
    add_member(two_tenants, "beta", "zhangsan")
    client = _client(two_tenants)
    login_at(client, "zhangsan")

    response = client.get("/api/auth/tenants")

    assert response.status_code == 200, response.text
    assert response.json()["data"] == [
        {"slug": "alpha", "name": "alpha 账套", "is_current": True},
        {"slug": "beta", "name": "beta 账套", "is_current": False},
    ]


def test_switch_tenant_moves_the_session(two_tenants):
    add_member(two_tenants, "alpha", "zhangsan")
    add_member(two_tenants, "beta", "zhangsan")
    client = _client(two_tenants)
    login_at(client, "zhangsan")
    assert client.post("/api/expenses", json=EXPENSE).status_code == 200

    response = client.post("/api/auth/switch-tenant", json={"slug": "beta"})

    assert response.status_code == 200, response.text
    assert response.json()["data"]["tenant"] == {"slug": "beta", "name": "beta 账套"}
    assert client.get("/api/expenses").json()["data"]["items"] == []
    assert client.post("/api/auth/switch-tenant", json={"slug": "alpha"}).status_code == 200
    merchants = [row["merchant"] for row in client.get("/api/expenses").json()["data"]["items"]]
    assert merchants == ["阿尔法便利店"]


def test_switch_to_foreign_tenant_is_forbidden(two_tenants):
    add_member(two_tenants, "alpha", "zhangsan")
    client = _client(two_tenants)
    login_at(client, "zhangsan")

    response = client.post("/api/auth/switch-tenant", json={"slug": "beta"})

    assert response.status_code == 403
    assert response.json()["error"] == "当前账号不属于该账套，请联系管理员开通"
    assert client.get("/api/expenses").status_code == 200  # 仍在原账套


def test_switch_to_unknown_or_malformed_tenant_is_rejected(two_tenants):
    add_member(two_tenants, "alpha", "zhangsan")
    client = _client(two_tenants)
    login_at(client, "zhangsan")

    assert client.post("/api/auth/switch-tenant", json={"slug": "ghost"}).status_code == 404
    assert client.post("/api/auth/switch-tenant", json={"slug": "../etc"}).status_code == 422
    assert client.post("/api/auth/switch-tenant", json={"slug": "Alpha"}).status_code == 422


def test_tenant_endpoints_require_login(two_tenants):
    """未登录时中间件在解析账套这一步就拦住（400 且文案提示重新登录），不会泄露账套列表。"""
    client = _client(two_tenants)

    listed = client.get("/api/auth/tenants")
    switched = client.post("/api/auth/switch-tenant", json={"slug": "alpha"})

    assert (listed.status_code, switched.status_code) == (400, 400)
    assert listed.json()["error"] == "无法确定当前账套，请重新登录"


def test_status_reports_tenant_in_saas(two_tenants):
    add_member(two_tenants, "alpha", "zhangsan")
    client = _client(two_tenants)

    before = client.get("/api/auth/status").json()["data"]
    login_at(client, "zhangsan")
    after = client.get("/api/auth/status").json()["data"]

    assert before == {
        "auth_enabled": True,
        "password_set": True,  # 统一域名尚未定位账套：直接显示登录表单
        "authenticated": False,
        "user": None,
        "multi_tenant": True,
        "tenant": None,
    }
    assert after["multi_tenant"] is True
    assert after["tenant"] == {"slug": "alpha", "name": "alpha 账套"}


def test_single_tenant_hides_every_tenant_concept(admin_client):
    status = admin_client.get("/api/auth/status").json()["data"]

    assert set(status) == {"auth_enabled", "password_set", "authenticated", "user"}
    assert admin_client.get("/api/auth/tenants").status_code == 404
    switch = admin_client.post("/api/auth/switch-tenant", json={"slug": "default"})
    assert switch.status_code == 404
    assert switch.json()["error"] == "当前为单账套部署，无需切换账套"
