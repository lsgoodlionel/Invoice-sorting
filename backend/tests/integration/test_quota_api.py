"""GET /api/quota：套餐、各项上限与用量、只读原因；单账套部署不制造假限制。"""

from datetime import timedelta

from sqlalchemy import select

from invoice_sorting.control.models import UsageSnapshot
from invoice_sorting.db.models import now
from invoice_sorting.quota.constants import KIND_EXPENSES, KIND_STORAGE, KIND_USERS
from invoice_sorting.quota.plans import FREE_PLAN
from tests.quota_helpers import fetch_quota, set_plan, update_tenant
from tests.tenancy_helpers import add_member, host_headers, open_tenants

PAYLOAD = {"spent_on": "2026-09-15", "amount_cents": 1200, "merchant": "阿尔法便利店"}
LINE_KEYS = {"key", "label", "unit", "limit", "used", "remaining", "is_unlimited", "is_exceeded"}


def test_quota_reports_plan_limits_and_usage(saas_app, saas_client):
    open_tenants(saas_app, "alpha")
    set_plan(saas_app, "alpha", max_users=5, max_storage_mb=10, max_expenses_per_month=50)
    add_member(saas_app, "alpha", "zhang")
    saas_client.post("/api/expenses", json=PAYLOAD, headers=host_headers("alpha"))

    data = fetch_quota(saas_client, host_headers("alpha"))

    assert data["enforced"] is True
    assert data["plan"]["name"] == "团队版"
    assert data["plan"]["max_users"] == 5
    assert {line["key"]: line["limit"] for line in data["limits"]} == {
        KIND_USERS: 5,
        KIND_STORAGE: 10,
        KIND_EXPENSES: 50,
    }
    assert {line["key"]: line["used"] for line in data["limits"]}[KIND_EXPENSES] == 1
    assert set(data["limits"][0]) == LINE_KEYS
    assert data["usage"]["expenses_this_month"] == 1
    assert data["usage"]["storage_bytes"] >= 0
    assert data["is_readonly"] is False and data["readonly_reason"] == ""


def test_tenant_without_plan_sees_the_builtin_free_plan(saas_app, saas_client):
    open_tenants(saas_app, "alpha")

    data = fetch_quota(saas_client, host_headers("alpha"))

    assert data["plan"]["code"] == FREE_PLAN.code
    assert data["plan"]["max_users"] == FREE_PLAN.max_users


def test_quota_reports_the_expiry_day_and_countdown(saas_app, saas_client):
    open_tenants(saas_app, "alpha")
    expires_on = now().date() + timedelta(days=9)
    update_tenant(saas_app, "alpha", expires_on=expires_on)

    data = fetch_quota(saas_client, host_headers("alpha"))

    assert data["expires_on"] == expires_on.isoformat()
    assert data["expires_in_days"] == 9
    assert data["is_readonly"] is False


def test_reading_quota_records_a_daily_usage_snapshot(saas_app, saas_client):
    open_tenants(saas_app, "alpha")
    saas_client.post("/api/expenses", json=PAYLOAD, headers=host_headers("alpha"))

    fetch_quota(saas_client, host_headers("alpha"))

    with saas_app.state.control_session_factory() as control:
        rows = list(control.scalars(select(UsageSnapshot)))
    assert len(rows) == 1
    assert (rows[0].day, rows[0].expenses_created) == (now().date(), 1)


def test_snapshot_keeps_one_row_per_day(saas_app, saas_client):
    open_tenants(saas_app, "alpha")
    headers = host_headers("alpha")
    fetch_quota(saas_client, headers)
    saas_client.post("/api/expenses", json=PAYLOAD, headers=headers)
    saas_app.state.quota_service.forget_snapshots()  # 跳过写入节流，模拟隔一段时间再看

    fetch_quota(saas_client, headers)

    with saas_app.state.control_session_factory() as control:
        rows = list(control.scalars(select(UsageSnapshot)))
    assert len(rows) == 1
    assert rows[0].expenses_created == 1


def test_single_tenant_deployment_reports_no_quota(client):
    data = fetch_quota(client)

    assert data["enforced"] is False
    assert data["plan"] is None
    assert data["limits"] == []
    assert data["usage"] is None
    assert data["is_readonly"] is False
