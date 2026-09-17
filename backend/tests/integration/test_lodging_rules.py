"""差旅交通：住宿酒店发票需附酒店订单，不再要求行程单；交通票照旧要求行程单。"""

from datetime import date

import pytest
from sqlalchemy import select

from invoice_sorting.checklist.service import condition_matches
from invoice_sorting.db.models import AppSetting, Category, ChecklistRule, Expense
from invoice_sorting.db.seed import LODGING_KEYWORDS, sync_default_rules
from invoice_sorting.expenses.service import create_expense, refresh_expense
from tests.invoice_factory import store_invoice


def category_id(session, name: str) -> int:
    return session.scalar(select(Category.id).where(Category.name == name))


def travel_expense(session, settings, tmp_path, *, tax_category: str, item: str, seller: str):
    expense = create_expense(
        session,
        settings,
        spent_on=date(2026, 6, 20),
        amount_cents=45000,
        merchant=seller,
        category_id=category_id(session, "差旅交通"),
    )
    store_invoice(
        session,
        settings,
        tmp_path,
        name=f"{item}.pdf",
        expense=expense,
        invoice={
            "invoice_no": f"2511700000{expense.id:010d}",
            "seller_name": seller,
            "item_summary": item,
            "tax_category": tax_category,
            "confirmed": True,
        },
    )
    session.flush()
    return refresh_expense(session, settings, expense)


def required_kinds(expense: Expense) -> dict[str, str]:
    return {item.attachment_kind: item.hint for item in expense.checklist_items}


def test_hotel_invoice_requires_order_not_itinerary(session, settings, tmp_path):
    expense = travel_expense(
        session,
        settings,
        tmp_path,
        tax_category="住宿服务",
        item="住宿费",
        seller="北京某某酒店有限公司",
    )

    kinds = required_kinds(expense)
    assert "order" in kinds and "酒店订单" in kinds["order"]
    assert "itinerary" not in kinds


def test_train_ticket_still_requires_itinerary_without_order(session, settings, tmp_path):
    expense = travel_expense(
        session,
        settings,
        tmp_path,
        tax_category="旅客运输服务",
        item="客运服务费",
        seller="享道出行",
    )

    kinds = required_kinds(expense)
    assert "itinerary" in kinds
    assert "order" not in kinds


@pytest.mark.parametrize(
    ("merchant", "expected"), [("全季酒店", True), ("某某宾馆", True), ("滴滴出行", False)]
)
def test_content_keywords_match_merchant_and_exclusion(session, settings, merchant, expected):
    expense = Expense(merchant=merchant, summary="", amount_cents=100, attachments=[])

    assert condition_matches({"content_keywords": list(LODGING_KEYWORDS)}, expense) is expected
    assert condition_matches({"exclude_keywords": list(LODGING_KEYWORDS)}, expense) is not expected


def test_rule_api_accepts_and_validates_keywords(client):
    body = {"attachment_kind": "order", "level": "required", "hint": "酒店订单"}
    ok_response = client.post(
        "/api/checklist-rules", json={**body, "condition": {"content_keywords": ["住宿", "酒店"]}}
    )
    assert ok_response.status_code == 200, ok_response.text
    assert ok_response.json()["data"]["condition"] == {"content_keywords": ["住宿", "酒店"]}

    bad = client.post(
        "/api/checklist-rules", json={**body, "condition": {"content_keywords": [""]}}
    )
    assert bad.status_code == 422


def test_existing_database_gets_lodging_rules_once(session):
    travel = category_id(session, "差旅交通")
    rules = session.scalars(select(ChecklistRule).where(ChecklistRule.category_id == travel)).all()
    for rule in rules:
        if rule.attachment_kind == "order":
            session.delete(rule)
        elif rule.attachment_kind == "itinerary":
            rule.condition = {}
    session.merge(AppSetting(key="rules_version", value="4"))
    session.commit()

    sync_default_rules(session)
    sync_default_rules(session)

    rules = session.scalars(select(ChecklistRule).where(ChecklistRule.category_id == travel)).all()
    orders = [rule for rule in rules if rule.attachment_kind == "order"]
    itinerary = next(rule for rule in rules if rule.attachment_kind == "itinerary")
    assert len(orders) == 1 and orders[0].condition == {"content_keywords": list(LODGING_KEYWORDS)}
    assert itinerary.condition == {"exclude_keywords": list(LODGING_KEYWORDS)}
