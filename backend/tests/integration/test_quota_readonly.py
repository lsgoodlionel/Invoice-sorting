"""租户状态只读降级：停用与到期各给各的文案；查看、导出、备份不受影响。"""

from datetime import timedelta

from invoice_sorting.control.models import TENANT_STATUS_CLOSED, TENANT_STATUS_SUSPENDED
from invoice_sorting.db.models import now
from invoice_sorting.licensing.guard import write_guards
from tests.quota_helpers import fetch_quota, update_tenant
from tests.tenancy_helpers import host_headers, open_tenants

PAYLOAD = {"spent_on": "2026-09-15", "amount_cents": 1200, "merchant": "阿尔法便利店"}
STATS_EXPORT = "/api/stats/export?start=2026-09-01&end=2026-09-30"


def create_expense(client, slug: str):
    return client.post("/api/expenses", json=PAYLOAD, headers=host_headers(slug))


def test_suspended_tenant_cannot_write_but_can_read(saas_app, saas_client):
    open_tenants(saas_app, "alpha")
    create_expense(saas_client, "alpha")
    update_tenant(saas_app, "alpha", status=TENANT_STATUS_SUSPENDED)

    blocked = create_expense(saas_client, "alpha")

    assert blocked.status_code == 403
    assert "账套已停用" in blocked.json()["error"]
    assert saas_client.get("/api/expenses", headers=host_headers("alpha")).status_code == 200


def test_closed_tenant_gets_its_own_wording(saas_app, saas_client):
    open_tenants(saas_app, "alpha")
    update_tenant(saas_app, "alpha", status=TENANT_STATUS_CLOSED)

    blocked = create_expense(saas_client, "alpha")

    assert blocked.status_code == 403
    assert "账套已关闭" in blocked.json()["error"]


def test_expired_tenant_is_readonly_with_expiry_wording(saas_app, saas_client):
    open_tenants(saas_app, "alpha")
    yesterday = now().date() - timedelta(days=1)
    update_tenant(saas_app, "alpha", expires_on=yesterday)

    blocked = create_expense(saas_client, "alpha")

    assert blocked.status_code == 403
    error = blocked.json()["error"]
    assert "订阅已到期" in error and yesterday.isoformat() in error
    assert "账套已停用" not in error


def test_tenant_expiring_today_can_still_write(saas_app, saas_client):
    open_tenants(saas_app, "alpha")
    update_tenant(saas_app, "alpha", expires_on=now().date())

    assert create_expense(saas_client, "alpha").status_code == 200


def test_readonly_tenant_can_still_export_and_backup(saas_app, saas_client):
    open_tenants(saas_app, "alpha")
    create_expense(saas_client, "alpha")
    update_tenant(saas_app, "alpha", status=TENANT_STATUS_SUSPENDED)
    headers = host_headers("alpha")

    assert saas_client.get(STATS_EXPORT, headers=headers).status_code == 200
    assert saas_client.post("/api/backup", headers=headers).status_code == 200


def test_quota_endpoint_explains_why_it_is_readonly(saas_app, saas_client):
    open_tenants(saas_app, "alpha")
    update_tenant(saas_app, "alpha", status=TENANT_STATUS_SUSPENDED)

    data = fetch_quota(saas_client, host_headers("alpha"))

    assert data["is_readonly"] is True
    assert data["readonly_reason"] == "tenant_suspended"
    assert "账套已停用" in data["readonly_message"]
    assert data["status"] == TENANT_STATUS_SUSPENDED


def test_restoring_the_tenant_takes_effect_immediately(saas_app, saas_client):
    """运营后台恢复账套后，下一次写请求就能通过，不需要重启或等缓存过期。"""
    open_tenants(saas_app, "alpha")
    update_tenant(saas_app, "alpha", status=TENANT_STATUS_SUSPENDED)
    assert create_expense(saas_client, "alpha").status_code == 403

    update_tenant(saas_app, "alpha", status="active")

    assert create_expense(saas_client, "alpha").status_code == 200


def test_license_guard_runs_before_quota_guard(saas_app):
    """守卫按注册顺序执行：授权先于额度，先命中先返回。"""
    names = [check.__name__ for check in write_guards(saas_app)]

    assert names == ["license_write_check", "quota_write_check"]
