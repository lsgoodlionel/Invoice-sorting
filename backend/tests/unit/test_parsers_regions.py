"""开票地区与订单号识别单测。"""

import pytest

from invoice_sorting.parsers.regions import PROVINCES, region_from_invoice
from invoice_sorting.parsers.text_utils import find_order_no


def test_province_table_has_31_entries():
    assert len(PROVINCES) == 31
    assert PROVINCES["65"] == "新疆"


@pytest.mark.parametrize(
    ("invoice_no", "expected"),
    [
        ("25317000000000000001", ("31", "上海")),
        ("25117000000000000002", ("11", "北京")),
        ("25127000000000000003", ("12", "天津")),
        ("25442000000000000004", ("44", "广东")),
        ("25617000000000000005", ("61", "陕西")),
        ("25217000000000000006", ("21", "辽宁")),
        ("25347000000000000007", ("34", "安徽")),
    ],
)
def test_digital_invoice_number_province(invoice_no, expected):
    assert region_from_invoice(invoice_no, "") == expected


@pytest.mark.parametrize(
    ("invoice_no", "expected"),
    [
        ("031001900111-12345678", ("31", "上海")),
        ("044031900111-12345678", ("44", "广东")),  # 深圳计划单列市归入广东
        ("021021900111-12345678", ("21", "辽宁")),  # 大连
        ("3100162130-12345678", ("31", "上海")),  # 10 位旧版纸票代码
    ],
)
def test_legacy_invoice_code_province(invoice_no, expected):
    assert region_from_invoice(invoice_no, "") == expected


@pytest.mark.parametrize(
    ("invoice_no", "tax_id", "expected"),
    [
        (None, "91310000MA1EXAMPLE", ("31", "上海")),
        ("12345678", "91110400MA0EXAMPLE", ("11", "北京")),
        ("25997000000000000000", "91440300MA0EXAMPLE", ("44", "广东")),
        (None, "310104123456789", ("31", "上海")),  # 15 位旧税号
        (None, "", ("", "")),
        (None, "91990000MA0EXAMPLE", ("", "")),
        ("099991900111-12345678", "", ("", "")),
    ],
)
def test_region_falls_back_to_seller_tax_id(invoice_no, tax_id, expected):
    assert region_from_invoice(invoice_no, tax_id) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("订单号:338600000001\n备\n注", "338600000001"),
        ("订单号：332400000002 SN/IMEI:8E00", "332400000002"),
        ("订单编号: ABC123", "ABC123"),
        ("备注 52100000003", ""),
    ],
)
def test_find_order_no(text, expected):
    assert find_order_no(text) == expected
