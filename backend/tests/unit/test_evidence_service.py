"""凭证识别入口与文字抽取：文件名回退、异常文件、PDF 文本层、OCR 集成（需安装 ocr 依赖）。"""

from datetime import date
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from invoice_sorting.evidence import ocr_available, recognize_evidence, service, text
from invoice_sorting.evidence.lines import EvidenceText, doc_from_rows

RECEIPT_LINES = [
    "Receipt",
    "Invoice number TEST0001-0001",
    "Receipt number 5555-6666",
    "Date paid March 5, 2026",
    "Example Labs, Inc.",
    "US$15.00 paid on March 5, 2026",
    "Description Qty Unit price Amount",
    "Example Pro 1 US$15.00 US$15.00",
    "Subtotal US$15.00",
    "Total US$15.00",
    "Amount paid US$15.00",
]


def _write_text_pdf(path: Path, lines: list[str]) -> Path:
    pdf = canvas.Canvas(str(path), pagesize=A4)
    for index, line in enumerate(lines):
        pdf.drawString(72, 780 - index * 20, line)
    pdf.save()
    return path


def _draw_image(rows: list[tuple[str, str | None]], size: tuple[int, int]) -> Image.Image:
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=40)
    for index, (left, right) in enumerate(rows):
        y = 60 + index * 90
        draw.text((40, y), left, fill="black", font=font)
        if right:
            draw.text((size[0] - 420, y), right, fill="black", font=font)
    return image


def test_text_pdf_receipt_is_recognized(tmp_path: Path) -> None:
    pdf = _write_text_pdf(tmp_path / "r.pdf", RECEIPT_LINES)
    result = recognize_evidence(pdf, "软件-Example-202603-收据.pdf")
    assert (result.doc_type, result.recognizer) == ("receipt", "receipt")
    assert (result.amount_cents, result.currency) == (1500, "USD")
    assert result.occurred_on == date(2026, 3, 5)
    assert result.order_no == "5555-6666"
    assert "Receipt number" in result.raw_text


def test_corrupt_image_returns_unknown(tmp_path: Path) -> None:
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not an image at all")
    result = recognize_evidence(broken, "坏图.png")
    assert (result.doc_type, result.recognizer) == ("unknown", "none")


def test_empty_pdf_falls_back_to_filename(tmp_path: Path) -> None:
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    result = recognize_evidence(empty, "办公-20260312-升降桌-459-交易订单.pdf")
    assert (result.doc_type, result.recognizer) == ("order", "filename")
    assert result.amount_cents == 45900
    assert result.cny_cents == 45900
    assert result.occurred_on == date(2026, 3, 12)


def test_missing_file_and_unsupported_type(tmp_path: Path) -> None:
    assert recognize_evidence(tmp_path / "nope.png", "x.png").doc_type == "unknown"
    other = tmp_path / "notes.txt"
    other.write_text("实付款 合计¥10")
    assert recognize_evidence(other, "notes.txt").recognizer == "none"


def test_unexpected_error_returns_unknown(monkeypatch, tmp_path: Path) -> None:
    def boom(path: Path) -> EvidenceText:
        raise RuntimeError("engine crashed")

    monkeypatch.setattr(service, "extract_text", boom)
    result = recognize_evidence(tmp_path / "a.png", "银行交易.png")
    assert (result.doc_type, result.recognizer) == ("unknown", "none")


def test_recognizer_result_is_completed_from_filename(monkeypatch, tmp_path: Path) -> None:
    rows = [["明细详情"], ["交易卡号(末四位)", "1234"], ["原始交易币种", "CNY"], ["入账详情"]]
    rows += [["境内外交易标识", "境内"], ["交易国家或地区", "中国"]]
    monkeypatch.setattr(service, "extract_text", lambda path: doc_from_rows(rows))
    result = recognize_evidence(tmp_path / "a.png", "办公-20260312-椅子-88.50-银行交易.png")
    assert result.recognizer == "bank_transaction"
    assert (result.amount_cents, result.cny_cents) == (8850, 8850)
    assert result.occurred_on == date(2026, 3, 12)


def test_itinerary_platform_taken_from_filename(monkeypatch, tmp_path: Path) -> None:
    ride_text = "申请日期: 2026-06-29 行程时间: 2026-06-22 至 2026-06-26\n共 2笔行程,合计46.80元"
    monkeypatch.setattr(service, "extract_text", lambda path: text.lines_from_text(ride_text))
    result = recognize_evidence(tmp_path / "a.pdf", "打车-【享道出行-46.80元】打车电子行程单.pdf")
    assert (result.recognizer, result.merchant) == ("ride_itinerary", "享道出行")


def test_raw_text_is_truncated(monkeypatch, tmp_path: Path) -> None:
    long_doc = doc_from_rows([["x" * 30000]])
    monkeypatch.setattr(service, "extract_text", lambda path: long_doc)
    assert len(recognize_evidence(tmp_path / "a.png", "a.png").raw_text) == service.RAW_TEXT_LIMIT


def test_image_without_ocr_has_no_text(monkeypatch, tmp_path: Path) -> None:
    image_path = tmp_path / "a.png"
    Image.new("RGB", (10, 10), "white").save(image_path)
    monkeypatch.setattr(text, "ocr_available", lambda: False)
    assert text.extract_text(image_path) == EvidenceText()


def test_limit_size_downscales_long_side() -> None:
    image = Image.new("RGB", (1200, 4800), "white")
    assert text.limit_size(image).size == (600, 2400)
    small = Image.new("RGB", (100, 100), "white")
    assert text.limit_size(small) is small


def test_render_broken_pdf_returns_none(tmp_path: Path) -> None:
    broken = tmp_path / "b.pdf"
    broken.write_bytes(b"%PDF-1.4 garbage")
    assert text.render_pdf_first_page(broken) is None


needs_ocr = pytest.mark.skipif(not ocr_available(), reason="未安装 ocr 可选依赖")


@needs_ocr
def test_ocr_image_rows_are_grouped_left_to_right(tmp_path: Path) -> None:
    rows = [
        ("Receipt", None),
        ("Receipt number 5555-6666", None),
        ("Date paid March 5, 2026", None),
        ("Subtotal", "US$15.00"),
        ("Total", "US$15.00"),
        ("Amount paid", "US$15.00"),
        ("Description", "Unit price"),
    ]
    image_path = tmp_path / "receipt.png"
    _draw_image(rows, (1300, 2600)).save(image_path)
    doc = text.extract_text(image_path)
    assert any(line.text.replace(" ", "").lower() == "totalus$15.00" for line in doc.lines)
    result = recognize_evidence(image_path, "receipt.png")
    assert result.recognizer == "receipt"
    assert (result.amount_cents, result.currency) == (1500, "USD")
    assert result.occurred_on == date(2026, 3, 5)


@needs_ocr
def test_scanned_pdf_uses_ocr(tmp_path: Path) -> None:
    rows = [("Receipt number 5555-6666", None), ("Amount paid", "US$15.00")]
    pdf_path = tmp_path / "scan.pdf"
    _draw_image(rows, (1300, 400)).save(pdf_path, "PDF")
    doc = text.extract_text(pdf_path)
    assert "5555-6666" in doc.text
