"""解析器注册表：按扩展名/文件头选择解析器，对外永不抛出异常。"""

import logging
import zipfile
from pathlib import Path

from invoice_sorting.parsers.air_itinerary import AirItineraryParser
from invoice_sorting.parsers.base import InvoiceParser, ParsedInvoice
from invoice_sorting.parsers.digital_pdf import DigitalPdfParser
from invoice_sorting.parsers.ground_travel import with_ground_travel
from invoice_sorting.parsers.ofd_invoice import (
    OfdInvoiceParser,
    invoice_xml_candidates,
    ofd_text,
)
from invoice_sorting.parsers.pdf_text import extract_pdf_text
from invoice_sorting.parsers.rail_ticket import RailTicketParser
from invoice_sorting.parsers.text_utils import contains_invoice_keyword
from invoice_sorting.parsers.xml_invoice import (
    SNIFF_BYTES,
    XmlInvoiceParser,
    looks_like_invoice_xml,
)

logger = logging.getLogger(__name__)

PDF_PARSERS: tuple[InvoiceParser, ...] = (
    AirItineraryParser(),
    RailTicketParser(),
    DigitalPdfParser(),
)
XML_PARSER = XmlInvoiceParser()
OFD_PARSER = OfdInvoiceParser()
DETECTION_PAGES = 2


def detect_kind(path: Path) -> str | None:
    """返回 "pdf" / "xml" / "ofd"，无法识别返回 None。"""
    suffix = path.suffix.lower()
    if suffix in (".pdf", ".xml", ".ofd"):
        return suffix[1:]
    try:
        with path.open("rb") as handle:
            head = handle.read(512)
    except OSError:
        return None
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"PK"):
        return "ofd"
    if head.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<"):
        return "xml"
    return None


def _has_valid_result(result: ParsedInvoice) -> bool:
    return result.invoice_no is not None or result.total_cents is not None


def _parse_pdf(path: Path) -> ParsedInvoice | None:
    text = extract_pdf_text(path)
    if not text:
        return None
    for parser in PDF_PARSERS:
        if parser.can_parse(path, text):
            return parser.parse(path, text)
    return None


def _parse_by_kind(path: Path, kind: str) -> ParsedInvoice | None:
    if kind == "pdf":
        return _parse_pdf(path)
    parser = XML_PARSER if kind == "xml" else OFD_PARSER
    if not parser.can_parse(path, None):
        return None
    return parser.parse(path, None)


def parse_invoice_file(path: Path) -> ParsedInvoice | None:
    """解析发票文件；加密/损坏/非发票返回 None，永不抛出异常。"""
    try:
        kind = detect_kind(path)
        result = _parse_by_kind(path, kind) if kind else None
    except Exception as exc:  # 解析器内部任何异常都不外抛
        logger.debug("发票解析失败 %s：%r", path, exc)
        return None
    if result is None or not _has_valid_result(result):
        return None
    return with_ground_travel(result)


def _xml_is_invoice(path: Path) -> bool:
    with path.open("rb") as handle:
        return looks_like_invoice_xml(handle.read(SNIFF_BYTES))


def _ofd_is_invoice(path: Path) -> bool:
    with zipfile.ZipFile(path) as archive:
        return bool(invoice_xml_candidates(archive)) or contains_invoice_keyword(ofd_text(archive))


def is_probably_invoice(path: Path) -> bool:
    """快速判断文件是否像发票（PDF 只读前两页文本）；出错返回 False。"""
    try:
        kind = detect_kind(path)
        if kind == "pdf":
            text = extract_pdf_text(path, max_pages=DETECTION_PAGES)
            return bool(text) and contains_invoice_keyword(text)
        if kind == "xml":
            return _xml_is_invoice(path)
        if kind == "ofd":
            return _ofd_is_invoice(path)
    except Exception as exc:  # 快速判断同样不外抛
        logger.debug("发票快速判断失败 %s：%r", path, exc)
    return False
