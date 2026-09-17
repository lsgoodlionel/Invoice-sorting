"""数电发票（全电）PDF 与增值税电子普通/专用发票 PDF 解析器。"""

from pathlib import Path

from invoice_sorting.parsers.base import InvoiceParseError, ParsedInvoice
from invoice_sorting.parsers.invoice_text import looks_like_vat_invoice, parse_invoice_text
from invoice_sorting.parsers.pdf_text import (
    extract_pdf_columns,
    extract_pdf_text,
    pdf_text_for_detection,
)


class DigitalPdfParser:
    name = "digital_pdf"

    def can_parse(self, path: Path, text: str | None) -> bool:
        content = pdf_text_for_detection(path, text)
        return bool(content) and looks_like_vat_invoice(content)

    def parse(self, path: Path, text: str | None) -> ParsedInvoice:
        content = text if text is not None else extract_pdf_text(path)
        if not content:
            raise InvoiceParseError(f"PDF 无可用文本：{path}")
        columns = extract_pdf_columns(path)
        return parse_invoice_text(content, self.name, columns)
