"""测试辅助：构造解析结果、空白 PDF 与待归属/已归属的发票附件。"""

from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium

from invoice_sorting.attachments.storage import store_file
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.db.models import Attachment, Expense, InvoiceData
from invoice_sorting.parsers import ParsedInvoice

BASE_PARSED = ParsedInvoice(
    invoice_no="26112000000000000001",
    issued_on=date(2026, 9, 10),
    total_cents=12800,
    tax_cents=1473,
    amount_cents=11327,
    seller_name="北京文具商行有限公司",
    seller_tax_id="91110000000000000X",
    buyer_name="",
    buyer_tax_id="",
    item_summary="笔记本",
    tax_category="纸制品",
    invoice_type="电子发票（普通发票）",
    parser="test",
    warnings=(),
    raw_text="发票",
    region_code="11",
    region_name="北京",
    order_no="",
)


def parsed_invoice(**overrides: Any) -> ParsedInvoice:
    return replace(BASE_PARSED, **overrides)


_counter = {"value": 0}


def blank_pdf(directory: Path, name: str = "发票.pdf") -> Path:
    """每次生成尺寸不同的空白 PDF，保证 sha256 不重复。"""
    _counter["value"] += 1
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{_counter['value']}_{name}"
    doc = pdfium.PdfDocument.new()
    doc.new_page(200 + _counter["value"], 300)
    doc.save(str(path))
    return path


def store_invoice(
    session,
    settings,
    directory: Path,
    *,
    name: str = "发票.pdf",
    invoice: dict[str, Any] | None = None,
    kind: AttachmentKind = AttachmentKind.INVOICE,
    expense: Expense | None = None,
) -> Attachment:
    """入库一个 PDF 附件；invoice 不为 None 时附带发票数据。"""
    attachment = store_file(session, settings, blank_pdf(directory, name), name, kind, expense)
    if invoice is not None:
        attachment.invoice_data = InvoiceData(**invoice)
    session.flush()
    return attachment
