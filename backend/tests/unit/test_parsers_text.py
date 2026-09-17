"""发票解析：大写金额、文本兜底、XML/OFD 边界情况的单测。"""

import zipfile
from datetime import date
from pathlib import Path

import pytest

from invoice_sorting.parsers import (
    InvoiceParseError,
    cn_upper_to_cents,
    parse_invoice_file,
    pdf_text,
)
from invoice_sorting.parsers.digital_pdf import DigitalPdfParser
from invoice_sorting.parsers.invoice_text import extract_parties, parse_invoice_text
from invoice_sorting.parsers.ofd_invoice import OfdInvoiceParser
from invoice_sorting.parsers.pdf_text import PdfColumns
from invoice_sorting.parsers.text_utils import parse_date, split_item_name, summarize_items
from invoice_sorting.parsers.xml_invoice import XmlInvoiceParser, parse_xml_bytes

INVOICES = Path(__file__).resolve().parents[1] / "fixtures" / "invoices"


@pytest.mark.parametrize(
    ("text", "cents"),
    [
        ("玖佰陆拾圆整", 96000),
        ("玖佰陆拾元正", 96000),
        ("壹万零伍拾圆零伍分", 1005005),
        ("叁佰贰拾壹圆肆角伍分", 32145),
        ("伍角", 50),
        ("零圆陆分", 6),
        ("拾圆整", 1000),
        ("壹拾贰万叁仟肆佰伍拾陆圆柒角捌分", 12345678),
        ("壹亿贰仟万圆整", 12000000000),
        ("贰佰", 20000),
    ],
)
def test_cn_upper_to_cents(text, cents):
    assert cn_upper_to_cents(text) == cents


@pytest.mark.parametrize("text", ["", "整", "玖佰ABC圆", "壹圆壹圆", "伍角叁"])
def test_cn_upper_to_cents_rejects_invalid(text):
    assert cn_upper_to_cents(text) is None


SAME_LINE_TEXT = """电子发票（普通发票）
发票号码：26312000000123456789
开票日期：2026年09月15日
购 名称：华东师范大学 销 名称：上海示例科技有限公司
买 纳税人识别号：12310000EXAMPLE001 售 统一社会信用代码/纳税人识别号：91310000MA1EXAMPLE
*计算机配套产品*鼠标 个 2 424.78 849.56 13% 110.44
合 计 ¥849.56 ¥110.44
价税合计（大写） ⓧ玖佰陆拾圆整 （小写）¥960.00
"""


def test_text_fallback_splits_same_line_parties_and_strips_vertical_labels():
    invoice = parse_invoice_text(SAME_LINE_TEXT, "digital_pdf")

    assert (invoice.buyer_name, invoice.buyer_tax_id) == ("华东师范大学", "12310000EXAMPLE001")
    assert (invoice.seller_name, invoice.seller_tax_id) == (
        "上海示例科技有限公司",
        "91310000MA1EXAMPLE",
    )
    assert invoice.issued_on == date(2026, 9, 15)
    assert invoice.warnings == ()


def test_text_fallback_keeps_empty_buyer_slot_for_individuals():
    text = "名称：个人 名称：上海示例科技有限公司\n纳税人识别号： 纳税人识别号：91310000MA1EXAMPLE"

    parties = extract_parties(text)

    assert (parties.buyer_name, parties.buyer_tax_id) == ("个人", "")
    assert (parties.seller_name, parties.seller_tax_id) == (
        "上海示例科技有限公司",
        "91310000MA1EXAMPLE",
    )


def test_columns_take_priority_over_reading_order():
    text = "名称：乙公司\n名称：甲大学"
    columns = PdfColumns(
        left="名称：甲大学\n纳税人识别号：12310000EXAMPLE001", right="名称：乙公司"
    )

    parties = extract_parties(text, columns)

    assert (parties.buyer_name, parties.seller_name) == ("甲大学", "乙公司")
    assert parties.buyer_tax_id == "12310000EXAMPLE001"


def test_columns_without_seller_fall_back_to_text():
    columns = PdfColumns(left="名称：甲大学", right="")

    parties = extract_parties("名称：甲大学 名称：乙公司", columns)

    assert (parties.buyer_name, parties.seller_name) == ("甲大学", "乙公司")


def test_sum_mismatch_and_missing_fields_are_warned():
    text = (
        "发票号码：26312000000123456789\n合 计 ¥800.00 ¥100.00\n"
        "价税合计（大写）玖佰圆整 （小写）¥960.00"
    )

    invoice = parse_invoice_text(text, "digital_pdf")

    assert "价税合计与金额+税额不一致" in invoice.warnings
    assert "大小写金额不一致" in invoice.warnings
    assert invoice.invoice_type == "数电发票"


def test_missing_total_number_and_unparseable_upper_are_warned():
    invoice = parse_invoice_text("价税合计（大写）玖佰整整圆圆 合 计 ¥1.00 ***", "digital_pdf")

    assert invoice.invoice_no is None
    assert "未识别到价税合计" in invoice.warnings
    assert "未识别到发票号码" in invoice.warnings
    assert invoice.invoice_type == ""


def test_tax_free_subtotal_counts_as_zero_tax():
    text = "发票号码：12345678\n合 计 ¥100.00 ***\n价税合计（大写）壹佰圆整（小写）¥100.00"

    invoice = parse_invoice_text(text, "digital_pdf")

    assert (invoice.amount_cents, invoice.tax_cents, invoice.total_cents) == (10000, 0, 10000)
    assert invoice.warnings == ()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-09-15 10:20:30", date(2026, 9, 15)),
        ("2026年9月5日", date(2026, 9, 5)),
        ("2026/13/01", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_date(text, expected):
    assert parse_date(text) == expected


def test_item_helpers():
    assert split_item_name("无分类项目") == ("", "无分类项目")
    assert summarize_items([]) == ("", "")
    assert summarize_items(["*餐饮服务*餐费", "*餐饮服务*饮料"]) == ("餐费等2项", "餐饮服务")


LOWERCASE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<inv:einvoice xmlns:inv="urn:example">
  <inv:invoicenumber>26312000000077778888</inv:invoicenumber>
  <inv:issuetime>2026年09月01日</inv:issuetime>
  <inv:buyername>华东师范大学</inv:buyername>
  <inv:sellername>上海示例科技有限公司</inv:sellername>
  <inv:totaltax-includedamount>100.00</inv:totaltax-includedamount>
  <inv:totalamwithouttax>90.00</inv:totalamwithouttax>
  <inv:totaltaxam>9.00</inv:totaltaxam>
  <inv:labelname>数电发票（增值税专用发票）</inv:labelname>
  <inv:itemname>咨询服务</inv:itemname>
</inv:einvoice>
"""


def test_xml_tags_match_case_and_namespace_insensitively():
    invoice = parse_xml_bytes(LOWERCASE_XML.encode("utf-8"))

    assert invoice.invoice_no == "26312000000077778888"
    assert invoice.issued_on == date(2026, 9, 1)
    assert invoice.invoice_type == "数电发票（增值税专用发票）"
    assert (invoice.item_summary, invoice.tax_category) == ("咨询服务", "")
    assert invoice.warnings == ("价税合计与金额+税额不一致",)


def test_xml_parser_accepts_text_argument():
    parser = XmlInvoiceParser()
    path = Path("inline.xml")

    assert parser.can_parse(path, LOWERCASE_XML) is True
    assert parser.parse(path, LOWERCASE_XML).buyer_name == "华东师范大学"


@pytest.mark.parametrize(
    "data",
    [
        b"<EInvoice><Other>1</Other></EInvoice>",
        b"<EInvoice><unclosed>",
        b'<!DOCTYPE x [<!ENTITY a "b">]><EInvoice><EIid>&a;</EIid></EInvoice>',
        b"<EInvoice>" + b" " * (5 * 1024 * 1024) + b"</EInvoice>",
    ],
)
def test_xml_unknown_malformed_dtd_or_oversized_raise_parse_error(data):
    with pytest.raises(InvoiceParseError):
        parse_xml_bytes(data)


def test_unknown_xml_file_returns_none(tmp_path):
    path = tmp_path / "unknown.xml"
    path.write_bytes(b"<EInvoice><Other>1</Other></EInvoice>")

    assert parse_invoice_file(path) is None


def test_oversized_xml_file_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / "big.xml"
    path.write_bytes(LOWERCASE_XML.encode("utf-8"))
    monkeypatch.setattr("invoice_sorting.parsers.xml_invoice.MAX_XML_BYTES", 10)

    assert XmlInvoiceParser().can_parse(path, None) is False
    with pytest.raises(InvoiceParseError):
        XmlInvoiceParser().parse(path, None)


def test_ofd_with_non_invoice_attachment_and_no_text_raises(tmp_path):
    path = tmp_path / "empty.ofd"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("OFD.xml", "<OFD/>")
        archive.writestr("Doc_0/Attachs/meta.xml", "<EInvoice><Other>1</Other></EInvoice>")

    with pytest.raises(InvoiceParseError):
        OfdInvoiceParser().parse(path, None)


def test_ofd_with_too_many_entries_or_bad_zip_raises(tmp_path, monkeypatch):
    bad = tmp_path / "bad.ofd"
    bad.write_bytes(b"PK not really a zip")
    monkeypatch.setattr("invoice_sorting.parsers.ofd_invoice.MAX_ENTRIES", 0)

    with pytest.raises(InvoiceParseError):
        OfdInvoiceParser().parse(bad, None)
    with pytest.raises(InvoiceParseError):
        OfdInvoiceParser().parse(INVOICES / "digital_with_xml.ofd", None)
    assert OfdInvoiceParser().can_parse(tmp_path / "x.zip", None) is False


def test_pdf_guards_reject_oversized_and_stop_on_time_budget(monkeypatch):
    sample = INVOICES / "digital_same_line.pdf"
    monkeypatch.setattr(pdf_text, "TIME_BUDGET_SECONDS", -1.0)
    assert pdf_text.extract_pdf_text(sample) is not None

    monkeypatch.setattr(pdf_text, "MAX_FILE_BYTES", 10)
    assert pdf_text.extract_pdf_text(sample) is None
    assert pdf_text.extract_pdf_columns(sample) is None


def test_pdf_columns_return_none_on_corrupt_pdf():
    assert pdf_text.extract_pdf_columns(INVOICES / "corrupt.pdf") is None


def test_digital_parser_raises_when_pdf_has_no_text():
    with pytest.raises(InvoiceParseError):
        DigitalPdfParser().parse(INVOICES / "corrupt.pdf", None)
