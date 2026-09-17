"""凭证识别：金额/币种、日期解析与文本行模型的单测。"""

from datetime import date

import pytest

from invoice_sorting.evidence.lines import (
    TextBox,
    doc_from_rows,
    lines_from_boxes,
    lines_from_text,
    value_after,
    value_below,
)
from invoice_sorting.evidence.parsing import (
    Money,
    find_all_dates,
    find_all_money,
    find_money,
    parse_date,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("¥144.26", Money(14426, "CNY")),
        ("￥ 459", Money(45900, "CNY")),
        ("US$20.00", Money(2000, "USD")),
        ("合计¥459>", Money(45900, "CNY")),
        ("消费144.26元，计入04月账单", Money(14426, "CNY")),
        ("共减¥16.8 合计¥19.62 >", Money(1680, "CNY")),
        ("HK$1,234.50", Money(123450, "HKD")),
        ("€9.99", Money(999, "EUR")),
        ("£5", Money(500, "GBP")),
        ("JP¥3,000", Money(300000, "JPY")),
        ("＄１２．５０", Money(1250, "USD")),
        ("USA-+15.00 USD 汇", Money(1500, "USD")),
        ("Total USD 7.00", Money(700, "USD")),
        ("RMB 88", Money(8800, "CNY")),
    ],
)
def test_find_money_parses_symbols_and_noise(text: str, expected: Money) -> None:
    assert find_money(text) == expected


def test_find_money_returns_none_without_currency_marker() -> None:
    assert find_money("订单编号 3434253000808809") is None
    assert find_money("") is None


def test_find_all_money_keeps_order() -> None:
    assert find_all_money("共减¥7.95 合计¥36.25") == [Money(795, "CNY"), Money(3625, "CNY")]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026年6月28日", date(2026, 6, 28)),
        ("2026-03-11 17:01:53", date(2026, 3, 11)),
        ("2026-03-1117:01:53", date(2026, 3, 11)),
        ("2026/3/5", date(2026, 3, 5)),
        ("Mar 5, 2026", date(2026, 3, 5)),
        ("March 5, 2026", date(2026, 3, 5)),
        ("Date paid 5 March 2026", date(2026, 3, 5)),
        ("２０２６年３月５日支付", date(2026, 3, 5)),
    ],
)
def test_parse_date_formats(text: str, expected: date) -> None:
    assert parse_date(text) == expected


def test_parse_date_rejects_invalid() -> None:
    assert parse_date("2026-13-40") is None
    assert parse_date(None) is None
    assert parse_date("无日期") is None


def test_find_all_dates_in_range() -> None:
    assert find_all_dates("行程时间: 2026-06-22 至 2026-06-26") == [
        date(2026, 6, 22),
        date(2026, 6, 26),
    ]


def test_lines_from_boxes_groups_rows_and_sorts_by_x() -> None:
    boxes = [
        TextBox("2026-04-01", 934, 1058, 1227, 1111),
        TextBox("交易时间", 86, 1053, 300, 1117),
        TextBox("明细详情", 544, 193, 772, 260),
        TextBox("RATECK", 84, 157, 132, 182),
    ]
    lines = lines_from_boxes(boxes)
    assert [line.text for line in lines] == ["RATECK", "明细详情", "交易时间 2026-04-01"]


def test_lines_from_boxes_skips_blank_text() -> None:
    assert lines_from_boxes([TextBox("  ", 0, 0, 10, 10)]) == ()


def test_lines_from_text_normalizes_fullwidth() -> None:
    doc = lines_from_text("订单编号：１２３\n\n  实付款 ￥459 ")
    assert doc.text == "订单编号:123\n实付款 ¥459"


def test_value_after_and_below() -> None:
    doc = doc_from_rows(
        [
            ["交易卡号(末四位)", "2123"],
            ["订单日期", "订单号"],
            ["2026年6月28日", "MLF2QL2F47"],
        ]
    )
    assert value_after(doc, r"交易卡号\(末四位\)") == "2123"
    assert value_below(doc, r"^订单号$") == "MLF2QL2F47"
    assert value_below(doc, r"^订单日期$") == "2026年6月28日"
    assert value_after(doc, "不存在") == ""
    assert value_below(doc, "不存在") == ""
