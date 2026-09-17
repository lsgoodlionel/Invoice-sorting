"""坐标版式解析（购销方、项目名称列、折扣行）与项目摘要规则单测。"""

from pathlib import Path

import pytest

from invoice_sorting.parsers import parse_invoice_file
from invoice_sorting.parsers.items import (
    InvoiceItem,
    items_from_text,
    join_wrapped_lines,
    summarize_invoice_items,
)
from invoice_sorting.parsers.layout import PageWords, Word, join_words
from invoice_sorting.parsers.layout_items import items_from_page
from invoice_sorting.parsers.layout_parties import parties_from_page
from invoice_sorting.parsers.parties import extract_text_parties
from invoice_sorting.parsers.pdf_text import extract_page_words

INVOICES = Path(__file__).resolve().parents[1] / "fixtures" / "invoices"
BUYER = "华东师范大学"
BUYER_ID = "12310000EXAMPLE001"


def word(x0: float, top: float, text: str, width: float | None = None) -> Word:
    size = 9.0
    return Word(x0, x0 + (width if width is not None else size * len(text)), top, top + size, text)


# ---------- 真实版式样本 ----------


def test_jd_layout_with_spaced_labels_and_wrapped_item_name():
    invoice = parse_invoice_file(INVOICES / "jd_spaced_labels.pdf")

    assert invoice is not None
    assert (invoice.buyer_name, invoice.buyer_tax_id) == (BUYER, BUYER_ID)
    assert (invoice.seller_name, invoice.seller_tax_id) == (
        "北京示例贸易有限公司",
        "91110000MA0EXAMPLE",
    )
    assert invoice.item_summary == "示例 DVI转HDMI转接头 DVI24+1/DVI-D双向互转显示器转换头 ZH-340"
    assert invoice.tax_category == "电线电缆"
    assert (invoice.region_code, invoice.region_name) == ("11", "北京")
    assert invoice.order_no == "338600000001"
    assert (invoice.total_cents, invoice.amount_cents, invoice.tax_cents) == (1290, 1142, 148)
    assert invoice.warnings == ()


def test_discount_lines_are_not_counted_as_items():
    invoice = parse_invoice_file(INVOICES / "discount_lines.pdf")

    assert invoice is not None
    assert (invoice.buyer_name, invoice.seller_name) == (BUYER, "上海示例贸易有限公司")
    assert invoice.seller_tax_id == "91310000MA5EXAMPLE"
    assert invoice.item_summary == "示例牌（DEMO）抽纸真抽纸M码无香4层90抽*18包纸巾餐巾纸等2项"
    assert invoice.tax_category == "纸制品"
    assert (invoice.region_code, invoice.region_name) == ("31", "上海")
    assert invoice.order_no == "317600000002"
    assert (invoice.total_cents, invoice.amount_cents, invoice.tax_cents) == (10823, 9578, 1245)
    assert invoice.warnings == ()


def test_page_words_expose_width_and_words():
    page = extract_page_words(INVOICES / "jd_spaced_labels.pdf")

    assert page is not None
    assert page.width > 500
    assert any(w.text == "项目名称" for w in page.words)


def test_page_words_none_for_corrupt_pdf():
    assert extract_page_words(INVOICES / "corrupt.pdf") is None


# ---------- 坐标购销方 ----------


def test_parties_from_page_same_column_legacy_layout():
    page = PageWords(
        600,
        (
            word(45, 100, "名称：甲大学"),
            word(45, 115, "纳税人识别号：12310000EXAMPLE001"),
            word(45, 300, "名称：乙公司"),
            word(45, 315, "纳税人识别号：91310000MA2EXAMPLE"),
        ),
    )

    parties = parties_from_page(page)

    assert parties is not None
    assert (parties.buyer_name, parties.buyer_tax_id) == ("甲大学", "12310000EXAMPLE001")
    assert (parties.seller_name, parties.seller_tax_id) == ("乙公司", "91310000MA2EXAMPLE")


def test_parties_from_page_keeps_spaces_in_english_names_and_ignores_invalid_ids():
    page = PageWords(
        600,
        (
            word(40, 100, "名"),
            word(55, 100, "称"),
            word(70, 100, "个人"),
            word(40, 115, "纳税人识别号："),
            word(330, 100, "名称："),
            word(380, 100, "Demo", 20),
            word(403, 100, "Trading", 30),
            word(330, 115, "统一社会信用代码/纳税人识别号：ABC"),
        ),
    )

    parties = parties_from_page(page)

    assert parties is not None
    assert (parties.buyer_name, parties.buyer_tax_id) == ("个人", "")
    assert (parties.seller_name, parties.seller_tax_id) == ("Demo Trading", "")


def test_parties_from_page_without_labels_returns_none():
    assert parties_from_page(PageWords(600, (word(40, 100, "其他"),))) is None


# ---------- 文本兜底购销方 ----------

JD_TEXT = """购 销
买 名 称 华东师范大学 售 名 称 北京示例贸易有限公司
: :
统一社会信用代码 纳税人识别号 12310000EXAMPLE001 统一社会信用代码 纳税人识别号 91110000MA0EXAMPLE
息 / : 息 / :
项目名称 规格型号 单位 数 量 单 价 金 额 税率/征收率 税 额
"""


def test_text_parties_tolerate_spaced_labels_and_colon_on_next_line():
    parties = extract_text_parties(JD_TEXT)

    assert (parties.buyer_name, parties.buyer_tax_id) == (BUYER, BUYER_ID)
    assert (parties.seller_name, parties.seller_tax_id) == (
        "北京示例贸易有限公司",
        "91110000MA0EXAMPLE",
    )


# ---------- 项目名称列 ----------


def header_words() -> list[Word]:
    return [word(58, 100, "项目名称"), word(160, 100, "规格型号"), word(450, 100, "金额")]


def test_items_from_page_joins_wrapped_names_and_flags_discounts():
    words = [
        *header_words(),
        word(25, 112, "*纸制品*甲", 40),
        word(160, 112, "X1"),
        word(310, 112, "1"),
        word(380, 112, "10.00"),
        word(450, 112, "10.00"),
        word(25, 122, "乙", 10),
        word(25, 134, "*纸制品*甲", 40),
        word(450, 134, "-2.00"),
        word(25, 144, "乙", 10),
        word(25, 156, "*纸制品*丙", 40),
        word(450, 156, "-1.00"),
        word(60, 200, "合"),
    ]

    items = items_from_page(PageWords(600, tuple(words)))

    assert items == [
        InvoiceItem("纸制品", "甲乙", False),
        InvoiceItem("纸制品", "甲乙", True),
        InvoiceItem("纸制品", "丙", True),
    ]


def test_items_from_page_without_header_or_items_returns_none():
    assert items_from_page(PageWords(600, (word(25, 112, "*纸制品*甲"),))) is None
    assert items_from_page(PageWords(600, (word(58, 100, "项目名称"),))) is None
    assert items_from_page(PageWords(600, tuple(header_words()))) is None


def test_join_words_uses_gaps_and_chinese_spacing_rule():
    words = [
        Word(0, 5, 0, 5, "W"),
        Word(5, 10, 0, 5, "I"),
        Word(12, 30, 0, 5, "抽纸"),
        Word(32, 40, 0, 5, "真"),
        Word(42, 60, 0, 5, "DDR5"),
        Word(62, 80, 0, 5, "4800"),
    ]

    assert join_words(words) == "WI 抽纸真 DDR5 4800"
    assert join_words([]) == ""


def test_join_wrapped_lines():
    assert join_wrapped_lines(["DVI-", "D转换", "DDR5", "4800"]) == "DVI-D转换DDR5 4800"


# ---------- 摘要规则 ----------


def test_summary_counts_only_regular_items_and_truncates_long_names():
    long_name = "长" * 61
    items = [
        InvoiceItem("", "折扣在前", True),
        InvoiceItem("图书", long_name, False),
        InvoiceItem("图书", long_name, True),
        InvoiceItem("图书", "乙", False),
    ]

    assert summarize_invoice_items(items) == ("长" * 60 + "…等2项", "图书")
    assert summarize_invoice_items([InvoiceItem("图书", "甲", True)]) == ("甲", "图书")
    assert summarize_invoice_items([]) == ("", "")


def test_items_from_text_detects_discount_rows():
    text = (
        "*纸制品*甲 箱 1 70.71 70.71 13% 9.19\n"
        "续行\n"
        "*纸制品*甲 -19.46 13% -2.53\n"
        "*印刷品*乙 -3.00 免税 ***\n"
        "*印刷品*丙 无 1 24 24.00 免税 ***\n"
    )

    assert items_from_text(text) == [
        InvoiceItem("纸制品", "甲", False),
        InvoiceItem("纸制品", "甲", True),
        InvoiceItem("印刷品", "乙", True),
        InvoiceItem("印刷品", "丙", False),
    ]


@pytest.mark.parametrize("name", ["digital_same_line.pdf", "vat_electronic_normal.pdf"])
def test_existing_layout_fixtures_still_use_coordinates(name):
    page = extract_page_words(INVOICES / name)

    assert page is not None
    assert parties_from_page(page) is not None
    assert items_from_page(page)
