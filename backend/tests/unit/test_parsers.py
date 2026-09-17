"""发票解析：基于虚构样本文件的端到端单测（样本由 scripts/make_invoice_fixtures.py 生成）。"""

import zipfile
from datetime import date
from pathlib import Path

import pytest

from invoice_sorting.parsers import ParsedInvoice, is_probably_invoice, parse_invoice_file
from invoice_sorting.parsers.air_itinerary import AirItineraryParser
from invoice_sorting.parsers.digital_pdf import DigitalPdfParser
from invoice_sorting.parsers.rail_ticket import RailTicketParser
from invoice_sorting.parsers.registry import detect_kind

INVOICES = Path(__file__).resolve().parents[1] / "fixtures" / "invoices"
BUYER = "华东师范大学"
BUYER_ID = "12310000EXAMPLE001"


def parse_fixture(name: str) -> ParsedInvoice:
    result = parse_invoice_file(INVOICES / name)
    assert result is not None, name
    return result


def test_digital_invoice_with_names_on_same_line():
    invoice = parse_fixture("digital_same_line.pdf")

    assert invoice.invoice_no == "26312000000123456789"
    assert invoice.issued_on == date(2026, 9, 15)
    assert (invoice.total_cents, invoice.amount_cents, invoice.tax_cents) == (96000, 84956, 11044)
    assert (invoice.buyer_name, invoice.buyer_tax_id) == (BUYER, BUYER_ID)
    assert (invoice.seller_name, invoice.seller_tax_id) == (
        "上海示例科技有限公司",
        "91310000MA1EXAMPLE",
    )
    assert (invoice.item_summary, invoice.tax_category) == ("鼠标", "计算机配套产品")
    assert invoice.invoice_type == "数电发票（普通发票）"
    assert invoice.parser == "digital_pdf"
    assert invoice.warnings == ()
    assert invoice.travel is None
    assert "价税合计" in invoice.raw_text


def test_digital_special_invoice_with_names_on_separate_lines_and_mixed_rates():
    invoice = parse_fixture("digital_multiline.pdf")

    assert invoice.invoice_no == "26312000000987654321"
    assert invoice.issued_on == date(2026, 8, 3)
    assert (invoice.total_cents, invoice.amount_cents, invoice.tax_cents) == (80000, 73719, 6281)
    assert (invoice.buyer_name, invoice.buyer_tax_id) == (BUYER, BUYER_ID)
    assert invoice.seller_name == "上海示例信息服务有限公司"
    assert invoice.seller_tax_id == "91310000MA3EXAMPLE"
    assert (invoice.item_summary, invoice.tax_category) == ("键盘等3项", "计算机配套产品")
    assert invoice.invoice_type == "数电发票（增值税专用发票）"
    assert invoice.warnings == ()


def test_legacy_vat_electronic_invoice_uses_code_and_number():
    invoice = parse_fixture("vat_electronic_normal.pdf")

    assert invoice.invoice_no == "031001900111-12345678"
    assert invoice.issued_on == date(2026, 3, 20)
    assert (invoice.total_cents, invoice.amount_cents, invoice.tax_cents) == (30000, 28302, 1698)
    assert (invoice.buyer_name, invoice.buyer_tax_id) == (BUYER, BUYER_ID)
    assert invoice.seller_name == "上海示例餐饮管理有限公司"
    assert invoice.seller_tax_id == "91310000MA2EXAMPLE"
    assert (invoice.item_summary, invoice.tax_category) == ("餐费", "餐饮服务")
    assert invoice.invoice_type == "增值税电子普通发票"
    assert invoice.warnings == ()


def test_upper_and_lower_amount_mismatch_is_warned():
    invoice = parse_fixture("digital_upper_mismatch.pdf")

    assert invoice.total_cents == 96000
    assert invoice.warnings == ("大小写金额不一致",)


def test_rail_ticket():
    invoice = parse_fixture("rail_ticket.pdf")

    assert invoice.parser == "rail_ticket"
    assert invoice.invoice_no == "26319000000087654321"
    assert invoice.issued_on == date(2026, 9, 10)
    assert invoice.total_cents == 13950
    assert invoice.seller_name == "中国铁路"
    assert (invoice.buyer_name, invoice.buyer_tax_id) == (BUYER, BUYER_ID)
    assert invoice.invoice_type == "电子发票（铁路电子客票）"
    assert invoice.item_summary == "上海虹桥-南京南 G7"
    assert invoice.travel == {
        "date": "2026-09-12",
        "from": "上海虹桥",
        "to": "南京南",
        "passenger": "张示例",
        "train_or_flight": "G7",
    }
    assert invoice.warnings == ()


def test_air_itinerary():
    invoice = parse_fixture("air_itinerary.pdf")

    assert invoice.parser == "air_itinerary"
    assert invoice.invoice_no == "26312000000055556666"
    assert invoice.issued_on == date(2026, 9, 8)
    assert invoice.total_cents == 108000
    assert invoice.seller_name == "上海示例航空票务有限公司"
    assert invoice.buyer_name == BUYER
    assert invoice.invoice_type == "电子发票（航空运输电子客票行程单）"
    assert invoice.travel == {
        "date": "2026-09-20",
        "from": "上海虹桥",
        "to": "北京首都",
        "passenger": "张示例",
        "train_or_flight": "MU5101",
    }


def test_digital_xml_invoice():
    invoice = parse_fixture("digital_invoice.xml")

    assert invoice.parser == "xml_invoice"
    assert invoice.invoice_no == "26312000000011112222"
    assert invoice.issued_on == date(2026, 9, 15)
    assert (invoice.total_cents, invoice.amount_cents, invoice.tax_cents) == (96000, 84956, 11044)
    assert (invoice.buyer_name, invoice.buyer_tax_id) == (BUYER, BUYER_ID)
    assert (invoice.seller_name, invoice.seller_tax_id) == (
        "上海示例科技有限公司",
        "91310000MA1EXAMPLE",
    )
    assert (invoice.item_summary, invoice.tax_category) == ("鼠标等2项", "计算机配套产品")
    assert invoice.invoice_type == "数电发票（普通发票）"
    assert invoice.warnings == ()


def test_ofd_prefers_attached_xml():
    invoice = parse_fixture("digital_with_xml.ofd")

    assert invoice.parser == "ofd_invoice"
    assert invoice.invoice_no == "26312000000033334444"
    assert invoice.total_cents == 96000
    assert invoice.seller_name == "上海示例科技有限公司"


def test_ofd_without_xml_falls_back_to_page_text():
    invoice = parse_fixture("digital_text_only.ofd")

    assert invoice.parser == "ofd_invoice"
    assert invoice.invoice_no == "26312000000987654321"
    assert invoice.issued_on == date(2026, 8, 3)
    assert invoice.total_cents == 80000
    assert (invoice.buyer_name, invoice.seller_name) == (BUYER, "上海示例信息服务有限公司")
    assert invoice.seller_tax_id == "91310000MA3EXAMPLE"
    assert invoice.item_summary == "键盘等3项"


@pytest.mark.parametrize("name", ["not_invoice.pdf", "corrupt.pdf", "encrypted.pdf"])
def test_non_invoice_corrupt_and_encrypted_pdf_return_none(name):
    assert parse_invoice_file(INVOICES / name) is None
    assert is_probably_invoice(INVOICES / name) is False


@pytest.mark.parametrize(
    "name",
    [
        "digital_same_line.pdf",
        "vat_electronic_normal.pdf",
        "rail_ticket.pdf",
        "air_itinerary.pdf",
        "digital_invoice.xml",
        "digital_with_xml.ofd",
        "digital_text_only.ofd",
    ],
)
def test_is_probably_invoice_accepts_invoices(name):
    assert is_probably_invoice(INVOICES / name) is True


def test_missing_file_returns_none_without_raising(tmp_path):
    missing = tmp_path / "missing.pdf"

    assert parse_invoice_file(missing) is None
    assert is_probably_invoice(missing) is False


def test_unknown_binary_returns_none(tmp_path):
    blob = tmp_path / "blob.bin"
    blob.write_bytes(b"\x00\x01binary")

    assert detect_kind(blob) is None
    assert parse_invoice_file(blob) is None
    assert is_probably_invoice(blob) is False


def test_content_sniffing_without_extension(tmp_path):
    pdf_copy = tmp_path / "invoice_download"
    pdf_copy.write_bytes((INVOICES / "digital_same_line.pdf").read_bytes())
    xml_copy = tmp_path / "invoice_xml"
    xml_copy.write_bytes((INVOICES / "digital_invoice.xml").read_bytes())
    ofd_copy = tmp_path / "invoice_ofd"
    ofd_copy.write_bytes((INVOICES / "digital_with_xml.ofd").read_bytes())

    assert parse_fixture_path(pdf_copy).invoice_no == "26312000000123456789"
    assert parse_fixture_path(xml_copy).invoice_no == "26312000000011112222"
    assert parse_fixture_path(ofd_copy).invoice_no == "26312000000033334444"


def parse_fixture_path(path: Path) -> ParsedInvoice:
    result = parse_invoice_file(path)
    assert result is not None
    return result


def test_non_invoice_xml_and_zip_return_none(tmp_path):
    xml_file = tmp_path / "config.xml"
    xml_file.write_text("<config><name>demo</name></config>", "utf-8")
    zip_file = tmp_path / "archive.ofd"
    with zipfile.ZipFile(zip_file, "w") as archive:
        archive.writestr("OFD.xml", "<OFD/>")

    assert parse_invoice_file(xml_file) is None
    assert is_probably_invoice(xml_file) is False
    assert parse_invoice_file(zip_file) is None
    assert is_probably_invoice(zip_file) is False


def test_pdf_parsers_extract_text_themselves_when_not_given():
    rail, air, digital = RailTicketParser(), AirItineraryParser(), DigitalPdfParser()
    ticket = INVOICES / "rail_ticket.pdf"

    assert rail.can_parse(ticket, None) is True
    assert air.can_parse(ticket, None) is False
    assert rail.parse(ticket, None).total_cents == 13950
    assert digital.parse(INVOICES / "digital_same_line.pdf", None).total_cents == 96000
    assert digital.can_parse(INVOICES / "digital_invoice.xml", None) is False


def test_fake_bold_duplicated_characters_are_deduplicated():
    # 真实发票用同位置重复绘制模拟粗体，抽取文本为“发发发票票票号号号码码码”
    result = parse_invoice_file(INVOICES / "fake_bold_labels.pdf")

    assert result is not None
    assert result.invoice_no == "26312000000123456789"
    assert result.total_cents == 96000
    assert result.buyer_name == "华东师范大学"
    assert result.seller_name
