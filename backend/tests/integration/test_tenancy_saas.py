"""SaaS 模式：按子域名定位租户，租户之间数据与目录完全隔离，未知租户明确报错。"""

from fastapi.testclient import TestClient

from invoice_sorting.main import create_app
from tests.conftest import make_saas_settings
from tests.tenancy_helpers import host_headers, open_tenants

PAYLOAD = {"spent_on": "2026-09-15", "amount_cents": 1200, "merchant": "阿尔法便利店"}


def _create_expense(client, slug: str, merchant: str) -> dict:
    response = client.post(
        "/api/expenses", json={**PAYLOAD, "merchant": merchant}, headers=host_headers(slug)
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _list_merchants(client, slug: str) -> list[str]:
    response = client.get("/api/expenses", headers=host_headers(slug))
    assert response.status_code == 200, response.text
    return [row["merchant"] for row in response.json()["data"]["items"]]


def test_two_tenants_cannot_see_each_other_records(saas_app, saas_client):
    open_tenants(saas_app, "alpha", "beta")

    _create_expense(saas_client, "alpha", "阿尔法便利店")
    _create_expense(saas_client, "beta", "贝塔书店")

    assert _list_merchants(saas_client, "alpha") == ["阿尔法便利店"]
    assert _list_merchants(saas_client, "beta") == ["贝塔书店"]


def test_each_tenant_has_its_own_directory(saas_app, saas_client, saas_settings):
    open_tenants(saas_app, "alpha", "beta")
    _create_expense(saas_client, "alpha", "阿尔法便利店")
    _create_expense(saas_client, "beta", "贝塔书店")

    tenants_dir = saas_settings.data_dir / "tenants"

    assert (tenants_dir / "alpha" / "invoice.db").exists()
    assert (tenants_dir / "beta" / "invoice.db").exists()
    assert not (saas_settings.data_dir / "invoice.db").exists()
    assert saas_settings.control_db_path.exists()


def test_unknown_tenant_is_rejected(saas_app, saas_client):
    open_tenants(saas_app, "alpha")

    response = saas_client.get("/api/expenses", headers=host_headers("unknown"))

    assert response.status_code == 404
    assert response.json()["error"] == "账套不存在"


def test_request_without_tenant_hint_is_rejected(saas_app, saas_client):
    open_tenants(saas_app, "alpha")

    response = saas_client.get("/api/expenses", headers={"Host": "example.com"})

    assert response.status_code == 400
    assert "账套" in response.json()["error"]


def test_saas_app_has_no_shared_business_session_factory(saas_app):
    """SaaS 模式不再预置全局业务库，避免任何路径回退到默认库。"""
    assert getattr(saas_app.state, "session_factory", None) is None
    assert getattr(saas_app.state, "engine", None) is None


def test_tenant_business_db_is_lazily_created(saas_app, saas_client, saas_settings):
    open_tenants(saas_app, "alpha", "beta")

    assert not (saas_settings.data_dir / "tenants" / "alpha").exists()

    _create_expense(saas_client, "alpha", "阿尔法便利店")

    assert (saas_settings.data_dir / "tenants" / "alpha" / "invoice.db").exists()
    assert not (saas_settings.data_dir / "tenants" / "beta").exists()


def test_settings_endpoint_reports_tenant_paths(saas_app, saas_client, saas_settings):
    open_tenants(saas_app, "alpha")

    response = saas_client.get("/api/settings", headers=host_headers("alpha"))

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["data_dir"] == str(saas_settings.data_dir / "tenants" / "alpha")


def test_health_stays_public_without_tenant(saas_client):
    response = saas_client.get("/api/health", headers={"Host": "example.com"})

    assert response.status_code == 200
    assert response.json()["data"] == {"status": "up"}


def test_auth_middleware_fails_closed_without_tenant(tmp_path):
    """开启认证的 SaaS 部署：拿不到租户时直接报错，绝不回退到任何默认库。"""
    app = create_app(make_saas_settings(tmp_path, auth_enabled=True))
    open_tenants(app, "alpha")
    with TestClient(app) as client:
        no_tenant = client.get("/api/expenses", headers={"Host": "example.com"})
        unknown = client.get("/api/expenses", headers=host_headers("unknown"))
        known = client.get("/api/expenses", headers=host_headers("alpha"))

    assert no_tenant.status_code == 400
    assert unknown.status_code == 404
    assert known.status_code == 401  # 租户找到了，但未登录
