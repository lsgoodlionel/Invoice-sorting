"""差旅票（铁路电子客票、航空行程单）解析器共用的构造逻辑。"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from invoice_sorting.parsers.base import InvoiceParseError, ParsedInvoice
from invoice_sorting.parsers.pdf_text import extract_pdf_text
from invoice_sorting.parsers.text_utils import (
    find_labeled_name,
    find_labeled_tax_id,
    normalize_text,
)

BUYER_NAME_LABELS = ("购买方名称", "购方名称")
BUYER_TAX_ID_LABELS = ("统一社会信用代码", "纳税人识别号")


@dataclass(frozen=True)
class TravelFields:
    invoice_no: str | None
    issued_on: date | None
    total_cents: int | None
    seller_name: str
    invoice_type: str
    date: str
    origin: str
    destination: str
    passenger: str
    train_or_flight: str


def pdf_text_or_raise(path: Path, text: str | None) -> str:
    content = text if text is not None else extract_pdf_text(path)
    if not content:
        raise InvoiceParseError(f"PDF 无可用文本：{path}")
    return content


def build_travel_invoice(fields: TravelFields, raw_text: str, parser_name: str) -> ParsedInvoice:
    text = normalize_text(raw_text)
    warnings = []
    if fields.invoice_no is None:
        warnings.append("未识别到发票号码")
    if fields.total_cents is None:
        warnings.append("未识别到票价/合计金额")
    route = "-".join(part for part in (fields.origin, fields.destination) if part)
    summary = " ".join(part for part in (route, fields.train_or_flight) if part)
    travel = {
        "date": fields.date,
        "from": fields.origin,
        "to": fields.destination,
        "passenger": fields.passenger,
        "train_or_flight": fields.train_or_flight,
    }
    return ParsedInvoice(
        invoice_no=fields.invoice_no,
        issued_on=fields.issued_on,
        total_cents=fields.total_cents,
        tax_cents=None,
        amount_cents=None,
        seller_name=fields.seller_name,
        seller_tax_id="",
        buyer_name=find_labeled_name(BUYER_NAME_LABELS, text),
        buyer_tax_id=find_labeled_tax_id(BUYER_TAX_ID_LABELS, text),
        item_summary=summary,
        tax_category="",
        invoice_type=fields.invoice_type,
        parser=parser_name,
        warnings=tuple(warnings),
        raw_text=raw_text,
        travel=travel,
    )
