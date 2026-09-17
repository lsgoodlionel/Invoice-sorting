"""地区设置接口：读写校验，修改本地地区或明细平台后重算未外发记录的清单。"""

from datetime import date

from sqlalchemy import select

from invoice_sorting.common.constants import ExpenseStatus
from invoice_sorting.db.models import Category, Expense
from invoice_sorting.expenses.recompute import refresh_open_expenses
from invoice_sorting.expenses.service import (
    create_expense,
    refresh_expense,
    set_status,
    soft_delete_expense,
)
from invoice_sorting.settings import router
from tests.invoice_factory import store_invoice


def data(response):
    assert response.status_code == 200, response.text
    return response.json()["data"]


def beijing_expense(session, settings, tmp_path, seller="北京文具商行有限公司"):
    other = session.scalar(select(Category.id).where(Category.name == "其他"))
    expense = create_expense(
        session,
        settings,
        spent_on=date(2026, 9, 10),
        amount_cents=12800,
        merchant="文具店",
        category_id=other,
    )
    store_invoice(
        session,
        settings,
        tmp_path,
        expense=expense,
        invoice={"region_name": "北京", "seller_name": seller, "confirmed": True},
    )
    refresh_expense(session, settings, expense)
    session.commit()
    return expense.id


def checklist_kinds(client, expense_id: int) -> set[str]:
    detail = data(client.get(f"/api/expenses/{expense_id}"))
    return {item["attachment_kind"] for item in detail["checklist"]}


def test_put_region_settings_validates_and_normalizes(client):
    updated = data(
        client.put(
            "/api/settings",
            json={"local_region": " 北京 ", "detail_platforms": ["京东", " 京东 ", "", "天猫"]},
        )
    )
    assert updated["local_region"] == "北京"
    assert updated["detail_platforms"] == ["京东", "天猫"]
    assert client.put("/api/settings", json={"local_region": "北" * 21}).status_code == 422
    assert client.put("/api/settings", json={"detail_platforms": "京东"}).status_code == 422


def test_changing_local_region_recomputes_checklists(client, session, settings, tmp_path):
    expense_id = beijing_expense(session, settings, tmp_path)
    detail = data(client.get(f"/api/expenses/{expense_id}"))
    assert detail["region_name"] == "北京" and detail["is_nonlocal"] is True
    assert "order" in checklist_kinds(client, expense_id)

    data(client.put("/api/settings", json={"local_region": "北京"}))

    assert "order" not in checklist_kinds(client, expense_id)
    assert data(client.get(f"/api/expenses/{expense_id}"))["is_nonlocal"] is False
    listed = data(client.get("/api/expenses"))["items"][0]
    assert listed["region_name"] == "北京" and listed["is_nonlocal"] is False


def test_changing_detail_platforms_recomputes_checklists(client, session, settings, tmp_path):
    expense_id = beijing_expense(session, settings, tmp_path)
    assert "order" in checklist_kinds(client, expense_id)

    data(client.put("/api/settings", json={"detail_platforms": ["文具商行"]}))

    assert "order" not in checklist_kinds(client, expense_id)


def test_unrelated_setting_does_not_recompute(client, monkeypatch):
    calls = []
    monkeypatch.setattr(router, "refresh_open_expenses", lambda *args: calls.append(args))
    data(client.put("/api/settings", json={"buyer_name": "某某大学", "local_region": "上海"}))
    assert calls == []


def test_refresh_open_expenses_skips_deleted_and_void(session, settings, tmp_path):
    kept = beijing_expense(session, settings, tmp_path)
    void = beijing_expense(session, settings, tmp_path, seller="北京甲公司")
    deleted = beijing_expense(session, settings, tmp_path, seller="北京乙公司")
    set_status(session, settings, session.get(Expense, void), ExpenseStatus.VOID, "个人消费")
    soft_delete_expense(session, settings, session.get(Expense, deleted))
    session.flush()

    assert refresh_open_expenses(session, settings) == 1
    assert session.get(Expense, kept).deleted is False


def test_rule_api_accepts_region_conditions(client):
    condition = {"is_nonlocal": True, "detail_platform": False, "amount_gte": 100}
    created = data(
        client.post(
            "/api/checklist-rules",
            json={"attachment_kind": "order", "condition": condition, "hint": "测试"},
        )
    )
    assert created["condition"] == condition
    bad = {"attachment_kind": "order", "condition": {"is_nonlocal": "yes"}}
    assert client.post("/api/checklist-rules", json=bad).status_code == 422
    rules = data(client.get("/api/checklist-rules"))
    defaults = [
        r for r in rules if r["condition"] == {"is_nonlocal": True, "detail_platform": False}
    ]
    assert len(defaults) == 1 and defaults[0]["level"] == "required"
