"""首页提醒 API：缺项、超期批次、久未开票、待归属附件、本月合计。"""

from datetime import date

import pytest

from invoice_sorting.attachments.storage import store_file
from invoice_sorting.stats.router import get_today
from tests.integration.test_batches_helpers import (
    add_items,
    category_id,
    make_batch,
    make_expense,
    png_bytes,
)

TODAY = date(2026, 9, 17)


@pytest.fixture
def dashboard(app, client):
    app.dependency_overrides[get_today] = lambda: TODAY

    def fetch() -> dict:
        response = client.get("/api/dashboard")
        assert response.status_code == 200, response.text
        return response.json()["data"]

    yield fetch
    app.dependency_overrides.clear()


def test_empty_dashboard(dashboard):
    data = dashboard()
    assert data == {
        "missing": [],
        "overdue": [],
        "spent_without_invoice": [],
        "unassigned_count": 0,
        "month_totals": {
            "spent_cents": 0,
            "pending_cents": 0,
            "in_transit_cents": 0,
            "reimbursed_cents": 0,
            "void_cents": 0,
        },
    }


def test_missing_and_spent_without_invoice(client, dashboard):
    consumables = category_id(client, "易耗品")
    old = make_expense(client, spent_on="2026-09-02", merchant="旧", with_invoice=False)
    recent = make_expense(client, spent_on="2026-09-03", merchant="新", with_invoice=False)
    lacking = make_expense(client, spent_on="2026-09-10", merchant="缺", category_id=consumables)
    make_expense(client, spent_on="2026-08-31", merchant="上月", cents=100)
    void = make_expense(client, spent_on="2026-09-01", merchant="作废", with_invoice=False)
    client.post(f"/api/expenses/{void['id']}/status", json={"status": "void", "note": "个人"})
    deleted = make_expense(client, spent_on="2026-09-01", merchant="删", with_invoice=False)
    client.delete(f"/api/expenses/{deleted['id']}")

    data = dashboard()
    assert [e["id"] for e in data["missing"]] == [lacking["id"], recent["id"], old["id"]]
    assert [e["id"] for e in data["spent_without_invoice"]] == [old["id"]]  # 早于 9/3
    totals = data["month_totals"]
    assert totals["spent_cents"] == 3 * 96000
    assert totals["void_cents"] == 96000
    assert totals["pending_cents"] == 3 * 96000


def test_missing_is_limited_to_twenty(client, dashboard):
    for index in range(21):
        make_expense(client, spent_on="2026-09-01", merchant=f"m{index}", with_invoice=False)
    assert len(dashboard()["missing"]) == 20


def test_overdue_batches_respect_setting(client, dashboard):
    batch = make_batch(client, "老批次")
    expense = make_expense(client)
    add_items(client, batch["id"], [expense["id"]])
    client.post(f"/api/batches/{batch['id']}/sent", json={"sent_on": "2026-08-10"})
    fresh = make_batch(client, "新批次")
    add_items(client, fresh["id"], [make_expense(client, merchant="b")["id"]])
    client.post(f"/api/batches/{fresh['id']}/sent", json={"sent_on": "2026-09-01"})

    assert [b["name"] for b in dashboard()["overdue"]] == ["老批次"]  # 默认 30 天
    client.put("/api/settings", json={"overdue_days": 10})
    assert [b["name"] for b in dashboard()["overdue"]] == ["老批次", "新批次"]
    client.post(f"/api/batches/{batch['id']}/received", json={"received_on": "2026-09-15"})
    assert [b["name"] for b in dashboard()["overdue"]] == ["新批次"]


def test_unassigned_count(app, settings, dashboard):
    source = settings.data_dir / "loose.png"
    source.write_bytes(png_bytes())
    with app.state.session_factory() as session:
        store_file(session, settings, source, "loose.png")
        session.commit()
    assert dashboard()["unassigned_count"] == 1


def test_default_today_is_shanghai_date():
    assert isinstance(get_today(), date)
