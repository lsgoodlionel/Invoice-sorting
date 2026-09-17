"""打印版 PDF 与命名规则单元测试（T10：图片页 A4、等比不变形）。"""

import io
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pypdfium2 as pdfium
import pytest
from PIL import Image
from pypdf import PdfReader

from invoice_sorting.exporter.naming import (
    PackageItem,
    kind_rank,
    package_items,
    support_name,
    unique_name,
)
from invoice_sorting.exporter.print_pdf import (
    A4_HEIGHT_PT,
    A4_WIDTH_PT,
    build_print_pdf,
    image_to_a4_pdf,
)
from tests.conftest import FIXTURES_DIR

RED_THRESHOLD = 200


def fake_attachment(att_id: int, mime: str, name: str, kind: str = "order"):
    return SimpleNamespace(id=att_id, mime=mime, original_name=name, kind=kind, invoice_data=None)


def fake_item(attachments, seq: int = 1, expense_id: int = 7):
    expense = SimpleNamespace(id=expense_id, merchant="京东", amount_cents=96000)
    return PackageItem(seq=seq, expense=expense, attachments=tuple(attachments))


def red_bbox(pdf_bytes: bytes) -> tuple[int, int]:
    """渲染第一页，返回红色像素区域的宽高。"""
    page = pdfium.PdfDocument(pdf_bytes)[0]
    image = page.render(scale=1).to_pil().convert("RGB")
    mask = Image.eval(image.split()[0], lambda v: 255 if v > RED_THRESHOLD else 0)
    green = Image.eval(image.split()[1], lambda v: 255 if v < 80 else 0)
    box = Image.composite(mask, Image.new("L", mask.size, 0), green).getbbox()
    assert box is not None
    return box[2] - box[0], box[3] - box[1]


@pytest.mark.parametrize(("size", "portrait"), [((400, 200), False), ((150, 600), True)])
def test_image_page_is_a4_and_keeps_aspect_ratio(tmp_path: Path, size, portrait):
    source = tmp_path / "pic.png"
    Image.new("RGB", size, (255, 0, 0)).save(source)
    pdf_bytes = image_to_a4_pdf(source)
    box = PdfReader(io.BytesIO(pdf_bytes)).pages[0].mediabox
    width, height = float(box.width), float(box.height)
    expected = (A4_WIDTH_PT, A4_HEIGHT_PT) if portrait else (A4_HEIGHT_PT, A4_WIDTH_PT)
    assert width == pytest.approx(expected[0], abs=1)
    assert height == pytest.approx(expected[1], abs=1)
    red_w, red_h = red_bbox(pdf_bytes)
    assert red_w / red_h == pytest.approx(size[0] / size[1], rel=0.02)
    assert red_w <= width and red_h <= height


def test_build_print_pdf_merges_and_skips(tmp_path: Path):
    image = tmp_path / "a.jpg"
    Image.new("RGB", (300, 500), "blue").save(image)
    files = {
        1: FIXTURES_DIR / "invoices" / "vat_electronic_normal.pdf",
        2: image,
        3: FIXTURES_DIR / "invoices" / "corrupt.pdf",
        4: FIXTURES_DIR / "invoices" / "digital_invoice.xml",
        5: tmp_path / "missing.png",
        6: FIXTURES_DIR / "invoices" / "encrypted.pdf",
    }
    attachments = [
        fake_attachment(1, "application/pdf", "发票.pdf", "invoice"),
        fake_attachment(2, "image/jpeg", "订单.jpg"),
        fake_attachment(3, "application/pdf", "坏.pdf"),
        fake_attachment(4, "application/xml", "发票.xml", "invoice"),
        fake_attachment(5, "image/png", "丢失.png"),
        fake_attachment(6, "application/pdf", "加密.pdf"),
    ]
    result = build_print_pdf([fake_item(attachments)], lambda a: files[a.id])
    pages = len(PdfReader(io.BytesIO(result.pdf_bytes)).pages)
    invoice_pages = len(PdfReader(files[1]).pages)
    assert pages == invoice_pages + 1
    assert result.skipped[7] == ["坏.pdf", "发票.xml", "丢失.png", "加密.pdf"]
    assert result.notes_for(7).startswith("坏.pdf 未合并到打印版")
    assert result.notes_for(99) == ""


def test_empty_print_pdf_has_blank_page():
    result = build_print_pdf([fake_item([])], lambda a: Path("/nope"))
    assert len(PdfReader(io.BytesIO(result.pdf_bytes)).pages) == 1


def test_naming_helpers():
    assert kind_rank("invoice") == 0
    assert kind_rank("unknown") == kind_rank("other")
    used: set[str] = set()
    assert unique_name("a/b.png", used) == "a/b.png"
    assert unique_name("a/b.png", used) == "a/b_2.png"
    item = fake_item([])
    attachment = fake_attachment(3, "image/png", "x.png", "payment")
    assert (
        support_name(item, attachment, 2, "by_kind") == "03_支撑材料/支付记录/01_京东_960.00_2.png"
    )
    assert (
        support_name(item, attachment, 1, "by_expense")
        == "03_支撑材料/01_京东_960.00/支付记录_1.png"
    )
    expenses = [
        SimpleNamespace(id=2, spent_on=date(2026, 9, 2), attachments=[]),
        SimpleNamespace(id=3, spent_on=date(2026, 9, 1), attachments=[]),
        SimpleNamespace(id=1, spent_on=date(2026, 9, 2), attachments=[]),
    ]
    assert [(i.seq, i.expense.id) for i in package_items(expenses)] == [(1, 3), (2, 1), (3, 2)]
