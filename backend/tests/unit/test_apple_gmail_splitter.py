from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from invoice_sorting.evidence.composite import CompositeSplitError, split_apple_gmail_pdf


def write_pdf(path: Path, pages: list[list[str]]) -> None:
    pdf = canvas.Canvas(str(path))
    for lines in pages:
        text = pdf.beginText(40, 800)
        for line in lines:
            text.textLine(line)
        pdf.drawText(text)
        pdf.showPage()
    pdf.save()


def test_splits_apple_gmail_receipts_and_keeps_cross_page_range(tmp_path: Path):
    source = tmp_path / "apple-thread.pdf"
    write_pdf(
        source,
        [
            ["Gmail - Your purchases from Apple", "Receipt", "October 1, 2026", "Order ID:", "ORDER-A1"],
            ["Receipt", "October 2, 2026", "Item B continues"],
            ["ORDER ID", "ORDER-B2", "Total USD 20.00"],
            ["Receipt", "October 3, 2026", "Order ID: ORDER-C3"],
        ],
    )

    parts = split_apple_gmail_pdf(source)

    assert [(part.order_no, part.start_page, part.end_page) for part in parts] == [
        ("ORDER-A1", 1, 1),
        ("ORDER-B2", 2, 3),
        ("ORDER-C3", 4, 4),
    ]
    assert "Item B continues" in parts[1].text
    assert "Total USD 20.00" in parts[1].text


def test_returns_empty_for_ordinary_pdf(tmp_path: Path):
    source = tmp_path / "ordinary.pdf"
    write_pdf(source, [["Receipt", "Order ID: ORDER-A1"]])

    assert split_apple_gmail_pdf(source) == []


def test_rejects_two_receipt_starts_on_one_page(tmp_path: Path):
    source = tmp_path / "ambiguous.pdf"
    write_pdf(
        source,
        [["Gmail - Your purchases from Apple", "Receipt", "Order ID: A1", "Receipt", "Order ID: B2"]],
    )

    with pytest.raises(CompositeSplitError, match="同一页包含多张 Apple 回执"):
        split_apple_gmail_pdf(source)
