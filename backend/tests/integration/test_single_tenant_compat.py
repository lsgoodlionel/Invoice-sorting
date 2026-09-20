"""单租户模式兼容：目录布局与老部署一致，业务接口照常工作，控制库只有 default 租户。"""

from sqlalchemy import select

from invoice_sorting.config import DEFAULT_TENANT_SLUG
from invoice_sorting.control.models import Tenant

PAYLOAD = {"spent_on": "2026-09-15", "amount_cents": 800, "merchant": "楼下超市"}


def test_business_files_stay_in_data_dir_root(app, settings):
    assert settings.db_path == settings.data_dir / "invoice.db"
    assert settings.db_path.exists()
    assert (settings.data_dir / "文件库").is_dir()
    assert not (settings.data_dir / "tenants").exists()


def test_control_db_is_created_next_to_business_db(app, settings):
    assert settings.control_db_path == settings.data_dir / "control.db"
    assert settings.control_db_path.exists()


def test_default_tenant_is_registered(app):
    with app.state.control_session_factory() as control:
        tenants = list(control.scalars(select(Tenant)))

    assert [tenant.slug for tenant in tenants] == [DEFAULT_TENANT_SLUG]
    assert tenants[0].status == "active"


def test_app_state_still_exposes_business_session_factory(app, settings):
    context = app.state.tenants.get(DEFAULT_TENANT_SLUG)

    assert app.state.session_factory is context.session_factory
    assert app.state.engine is context.engine
    assert context.settings.data_dir == settings.data_dir


def test_subdomain_is_ignored_in_single_mode(client):
    created = client.post("/api/expenses", json=PAYLOAD, headers={"Host": "whatever.example.com"})
    assert created.status_code == 200, created.text

    listed = client.get("/api/expenses", headers={"Host": "other.example.com"})

    assert listed.status_code == 200
    assert [row["merchant"] for row in listed.json()["data"]["items"]] == ["楼下超市"]


def test_settings_endpoint_reports_root_data_dir(client, settings):
    response = client.get("/api/settings")

    assert response.status_code == 200, response.text
    assert response.json()["data"]["data_dir"] == str(settings.data_dir)
