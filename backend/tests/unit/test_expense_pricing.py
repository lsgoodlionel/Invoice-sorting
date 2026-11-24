"""订单/发票数量识别与默认单价。"""

from types import SimpleNamespace

import pytest

from invoice_sorting.expenses.pricing import apply_default_pricing, infer_quantity


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
