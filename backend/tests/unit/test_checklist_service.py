"""凭证清单：规则条件、合并、同步（蓝图 T04/T05/T08）。"""

from datetime import date
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import select

from invoice_sorting.attachments.storage import store_file, trash_attachment
from invoice_sorting.checklist.service import (
    compute_checklist,
    evaluate_rules,
    required_missing_count,
)
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.db.models import Category, ChecklistRule
from invoice_sorting.expenses.service import create_expense, update_expense


def category_id(session, name: str) -> int:
    return session.scalar(select(Category.id).where(Category.name == name))


def new_expense(session, settings, amount_cents: int, category: str | None, **extra):
    return create_expense(
        session,
        settings,
        spent_on=date(2026, 9, 15),
        amount_cents=amount_cents,
        merchant="京东",
        category_id=category_id(session, category) if category else None,
        **extra,
    )


def items_by_kind(expense) -> dict[str, object]:
    return {item.attachment_kind: item for item in expense.checklist_items}


def add_file(session, settings, tmp_path: Path, expense, kind: AttachmentKind, color="red"):
    src = tmp_path / f"{kind}_{color}.png"
    Image.new("RGB", (10, 10), color).save(src)
    return store_file(session, settings, src, src.name, kind, expense)


def test_consumables_960_has_order_and_acceptance_but_no_payment(session, settings):
    expense = new_expense(session, settings, 96000, "易耗品")
    kinds = items_by_kind(expense)
    assert {"invoice", "order", "acceptance"} <= set(kinds)
    assert "payment" not in kinds


@pytest.mark.parametrize(("amount", "has_payment"), [(99999, False), (100000, True)])
def test_payment_record_threshold_is_inclusive_at_1000(session, settings, amount, has_payment):
    expense = new_expense(session, settings, amount, "其他")
    kinds = items_by_kind(expense)
    assert ("payment" in kinds) is has_payment
    if has_payment:
        assert kinds["payment"].level == "required"


def test_office_supplies_online_triggers_order(session, settings):
    offline = new_expense(session, settings, 2000, "办公用品")
    assert "order" not in items_by_kind(offline)

    online = new_expense(session, settings, 2000, "办公用品", is_online=True)
    assert items_by_kind(online)["order"].level == "required"


def test_rules_for_same_kind_merge_to_strictest_with_joined_hints(session, settings):
    session.add(
        ChecklistRule(
            category_id=category_id(session, "办公用品"),
            attachment_kind="acceptance",
            level="suggested",
            condition={},
            hint="建议附验收",
        )
    )
    session.add(
        ChecklistRule(
            category_id=None,
            attachment_kind="acceptance",
            level="required",
            condition={"amount_lt": 10000},
            hint="小额也要验收",
        )
    )
    session.flush()
    expense = new_expense(session, settings, 60000, "办公用品", is_online=True)

    rules = {rule.attachment_kind: rule for rule in evaluate_rules(session, expense)}

    assert rules["order"].level == "required"
    assert "网购办公用品需附机打订单清单" in rules["order"].hint
    assert "≥500元需附明细清单" in rules["order"].hint
    assert rules["acceptance"].level == "suggested"  # amount_lt 不满足
    update_expense(session, settings, expense, amount_cents=5000)
    rules = {rule.attachment_kind: rule for rule in evaluate_rules(session, expense)}
    assert rules["acceptance"].level == "required"
    assert "建议附验收" in rules["acceptance"].hint


def test_attachment_marks_item_present_and_removal_returns_missing(session, settings, tmp_path):
    expense = new_expense(session, settings, 96000, "易耗品")
    before = required_missing_count(expense)

    order = add_file(session, settings, tmp_path, expense, AttachmentKind.ORDER)
    compute_checklist(session, expense)
    assert items_by_kind(expense)["order"].state == "present"
    assert required_missing_count(expense) == before - 1

    trash_attachment(session, settings, order)
    compute_checklist(session, expense)
    assert items_by_kind(expense)["order"].state == "missing"


def test_not_needed_items_are_kept_when_rules_change(session, settings):
    expense = new_expense(session, settings, 96000, "易耗品")
    items_by_kind(expense)["order"].state = "not_needed"
    items_by_kind(expense)["order"].reason = "票面已含明细"

    update_expense(
        session, settings, expense, category_id=category_id(session, "办公用品"), is_online=True
    )

    kinds = items_by_kind(expense)
    assert kinds["order"].state == "not_needed"
    assert kinds["order"].reason == "票面已含明细"
    assert "acceptance" not in kinds  # 不再触发且仍缺少 → 删除


def test_not_needed_item_kept_even_when_no_longer_triggered(session, settings):
    expense = new_expense(session, settings, 96000, "易耗品")
    items_by_kind(expense)["acceptance"].state = "not_needed"

    update_expense(session, settings, expense, category_id=category_id(session, "其他"))

    assert items_by_kind(expense)["acceptance"].state == "not_needed"
    assert "order" not in items_by_kind(expense)


def test_required_missing_count_ignores_suggested_and_not_needed(session, settings):
    expense = new_expense(session, settings, 1000, "餐饮会议")
    kinds = items_by_kind(expense)
    assert kinds["meal_form"].level == "suggested"
    assert required_missing_count(expense) == 1  # 仅发票
    kinds["invoice"].state = "not_needed"
    assert required_missing_count(expense) == 0
