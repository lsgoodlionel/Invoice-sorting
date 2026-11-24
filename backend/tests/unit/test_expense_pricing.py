"""订单/发票数量识别与默认单价。"""

from datetime import date
from types import SimpleNamespace

import pytest

from invoice_sorting.db.models import Attachment, EvidenceData, Expense
from invoice_sorting.expenses.pricing import (
    apply_default_pricing,
    backfill_expense_display_fields,
    infer_quantity,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("打印纸×12", 12),
        ("签字笔 20支", 20),
        ("数量：100", 100),
        ("2件装", 2),
        ("型号 X2026", 1),
        ("订单号 123456", 1),
        ("101件", 1),
    ],
)
def test_infer_quantity_only_accepts_explicit_1_to_100(text, expected):
    assert infer_quantity([text]) == expected


def attachment(att_id, kind, *, evidence_name="", invoice_name=""):
    return SimpleNamespace(
        id=att_id,
        kind=kind,
        evidence_data=SimpleNamespace(item_name=evidence_name) if evidence_name else None,
        invoice_data=SimpleNamespace(item_summary=invoice_name) if invoice_name else None,
    )


def expense(*, cents=10000, item_name="", summary="", attachments=None, manual=False):
    return SimpleNamespace(
        amount_cents=cents,
        item_name=item_name,
        summary=summary,
        attachments=attachments or [],
        pricing_manual=manual,
        quantity=None,
        unit_price_cents=None,
    )


def test_order_quantity_has_priority_and_calculates_unit_price():
    row = expense(
        cents=10001,
        item_name="发票项目 2件",
        attachments=[attachment(1, "order", evidence_name="办公用品×4")],
    )

    apply_default_pricing(row)

    assert (row.quantity, row.unit_price_cents) == (4, 2500)


def test_invoice_quantity_is_used_when_order_has_no_quantity():
    row = expense(
        cents=12000,
        attachments=[attachment(1, "invoice", invoice_name="笔记本 6本")],
    )

    apply_default_pricing(row)

    assert (row.quantity, row.unit_price_cents) == (6, 2000)


def test_default_is_one_and_manual_pricing_is_preserved():
    default = expense(cents=8800, item_name="普通商品")
    apply_default_pricing(default)
    assert (default.quantity, default.unit_price_cents) == (1, 8800)

    manual = expense(cents=8800, item_name="商品×8", manual=True)
    manual.quantity, manual.unit_price_cents = 2, 4400
    apply_default_pricing(manual)
    assert (manual.quantity, manual.unit_price_cents) == (2, 4400)


def test_backfill_only_fills_missing_historical_fields(session):
    missing = Expense(
        spent_on=date(2026, 1, 2), amount_cents=12000, merchant="办公商城", summary=""
    )
    order = Attachment(
        kind="order", file_path="order.png", original_name="订单.png", sha256="q" * 64
    )
    order.evidence_data = EvidenceData(item_name="签字笔×4")
    missing.attachments.append(order)
    existing = Expense(
        spent_on=date(2026, 1, 3),
        amount_cents=9999,
        merchant="已有数据",
        summary="不应覆盖",
        item_name="人工名称",
        quantity=3,
        unit_price_cents=3333,
    )
    session.add_all([missing, existing])
    session.commit()

    assert backfill_expense_display_fields(session) == 1
    session.refresh(missing)
    session.refresh(existing)
    assert (missing.item_name, missing.quantity, missing.unit_price_cents) == ("签字笔×4", 4, 3000)
    assert (existing.item_name, existing.quantity, existing.unit_price_cents) == (
        "人工名称",
        3,
        3333,
    )
