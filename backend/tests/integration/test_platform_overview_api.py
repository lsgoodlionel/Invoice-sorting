"""平台概览：账套与账号统计；单账套部署下管理员照常可用（没有平台概念）。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from invoice_sorting.control.models import Tenant, UsageSnapshot
from invoice_sorting.db.models import now
from invoice_sorting.main import create_app
from tests.auth_helpers import setup_password
from tests.conftest import make_settings
from tests.platform_helpers import login_platform, platform_app

OVERVIEW = "/api/platform/overview"


@pytest.fixture
def app(tmp_path):
    return platform_app(tmp_path)


def write_snapshot(app, slug: str, *, storage_bytes: int, expenses: int, day=None) -> None:
    with app.state.control_session_factory() as control:
        tenant = control.scalar(select(Tenant).where(Tenant.slug == slug))
        control.add(
            UsageSnapshot(
                tenant_id=tenant.id,
                day=day or now().date(),
                users=1,
                storage_bytes=storage_bytes,
                expenses_created=expenses,
            )
        )
        control.commit()


def test_counts_tenants_and_accounts(app):
    client = login_platform(app)

    data = client.get(OVERVIEW).json()["data"]

    assert data["tenants"] == 3 and data["active_tenants"] == 3
    assert data["accounts"] == 3


def test_suspended_tenants_are_not_counted_as_active(app):
    client = login_platform(app)
    client.patch("/api/platform/tenants/beta", json={"status": "suspended"})

    data = client.get(OVERVIEW).json()["data"]

    assert data["tenants"] == 3 and data["active_tenants"] == 2


def test_usage_totals_come_from_the_latest_snapshot(app):
    from datetime import timedelta

    yesterday = now().date() - timedelta(days=1)
    write_snapshot(app, "alpha", storage_bytes=100, expenses=2, day=yesterday)
    write_snapshot(app, "alpha", storage_bytes=500, expenses=7)
    write_snapshot(app, "beta", storage_bytes=300, expenses=1)
    client = login_platform(app)

    data = client.get(OVERVIEW).json()["data"]

    assert data["storage_bytes"] == 800 and data["expenses_created"] == 8


def test_tenant_list_shows_the_latest_usage(app):
    write_snapshot(app, "alpha", storage_bytes=500, expenses=7)
    client = login_platform(app)

    items = client.get("/api/platform/tenants").json()["data"]["items"]
    alpha = next(item for item in items if item["slug"] == "alpha")

    assert alpha["usage"]["storage_bytes"] == 500
    assert alpha["usage"]["expenses_created"] == 7
    assert next(item for item in items if item["slug"] == "beta")["usage"] is None


def test_single_tenant_admin_can_read_overview(tmp_path):
    """单账套部署没有平台概念：管理员即平台管理员，接口不应 403。"""
    app = create_app(make_settings(tmp_path, auth_enabled=True))
    client = TestClient(app)
    setup_password(client)

    response = client.get(OVERVIEW)

    assert response.status_code == 200, response.text
    assert response.json()["data"]["tenants"] == 1
