"""数电发票 XML 解析器：标签名宽松匹配（忽略命名空间与大小写）。"""

import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from invoice_sorting.parsers.base import InvoiceParseError, ParsedInvoice
from invoice_sorting.parsers.cn_amount import cn_upper_to_cents
from invoice_sorting.parsers.invoice_text import amount_warnings
from invoice_sorting.parsers.items import summarize_items
from invoice_sorting.parsers.regions import region_from_invoice
from invoice_sorting.parsers.text_utils import find_order_no, parse_date, to_cents

logger = logging.getLogger(__name__)

MAX_XML_BYTES = 5 * 1024 * 1024
SNIFF_BYTES = 64 * 1024
FORBIDDEN_DTD = re.compile(rb"<!(?:DOCTYPE|ENTITY)", re.IGNORECASE)
XML_MARKERS: tuple[bytes, ...] = (b"einvoice", b"invoicenumber", b"eiid")

INVOICE_NO_TAGS = ("eiid", "invoicenumber", "invoiceno", "fphm")
ISSUED_TAGS = ("issuetime", "requesttime", "invoicedate", "kprq")
UPPER_TOTAL_TAGS = ("totaltax-includedamountinchinese", "jshjdx")
TOTAL_TAGS = ("totaltax-includedamount", "totaltaxincludedamount", "jshj")
AMOUNT_TAGS = ("totalamwithouttax", "totalamount", "hjje")
TAX_TAGS = ("totaltaxam", "totaltaxamount", "hjse")
BUYER_NAME_TAGS = ("buyername", "gmfmc")
BUYER_ID_TAGS = ("buyeridnum", "buyertaxid", "gmfnsrsbh")
SELLER_NAME_TAGS = ("sellername", "xsfmc")
SELLER_ID_TAGS = ("selleridnum", "sellertaxid", "xsfnsrsbh")
ITEM_NAME_TAGS = ("itemname", "xmmc")
TYPE_NAME_TAGS = ("labelname", "invoicetypename")


def local_name(tag: object) -> str:
    """去掉 “{namespace}” 或 “ns:” 前缀并转小写。"""
    name = str(tag).rsplit("}", 1)[-1]
    return name.rsplit(":", 1)[-1].lower()


def _first_text(root: ET.Element, tags: tuple[str, ...]) -> str:
    for tag in tags:
        for element in root.iter():
            if local_name(element.tag) == tag and element.text and element.text.strip():
                return element.text.strip()
    return ""


def _all_texts(root: ET.Element, tags: tuple[str, ...]) -> list[str]:
    return [
        element.text.strip()
        for element in root.iter()
        if local_name(element.tag) in tags and element.text and element.text.strip()
    ]


def _invoice_type(root: ET.Element) -> str:
    label = _first_text(root, TYPE_NAME_TAGS)
    if not label:
        return "数电发票"
    return label if label.startswith(("数电", "电子发票", "增值税")) else f"数电发票（{label}）"


def looks_like_invoice_xml(data: bytes) -> bool:
    head = re.sub(rb"\s+", b"", data[:SNIFF_BYTES].removeprefix(b"\xef\xbb\xbf")).lower()
    return head.startswith(b"<") and any(marker in head for marker in XML_MARKERS)


def parse_xml_bytes(
    data: bytes, raw_text: str | None = None, parser_name: str = "xml_invoice"
) -> ParsedInvoice:
    """解析发票 XML 字节；不是发票结构时抛 InvoiceParseError。"""
    if len(data) > MAX_XML_BYTES:
        raise InvoiceParseError("XML 过大")
    if FORBIDDEN_DTD.search(data[:SNIFF_BYTES]):
        raise InvoiceParseError("XML 含 DTD/实体声明，拒绝解析")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise InvoiceParseError(f"XML 无法解析：{exc}") from exc
    return _build_invoice(root, raw_text or data.decode("utf-8", "replace"), parser_name)


def _build_invoice(root: ET.Element, raw_text: str, parser_name: str) -> ParsedInvoice:
    invoice_no = _first_text(root, INVOICE_NO_TAGS) or None
    total = to_cents(_first_text(root, TOTAL_TAGS))
    if invoice_no is None and total is None:
        raise InvoiceParseError("XML 中未找到发票号码或价税合计")
    amount = to_cents(_first_text(root, AMOUNT_TAGS))
    tax = to_cents(_first_text(root, TAX_TAGS))
    upper = cn_upper_to_cents(_first_text(root, UPPER_TOTAL_TAGS))
    summary, category = summarize_items(_all_texts(root, ITEM_NAME_TAGS))
    seller_tax_id = _first_text(root, SELLER_ID_TAGS)
    region_code, region_name = region_from_invoice(invoice_no, seller_tax_id)
    return ParsedInvoice(
        invoice_no=invoice_no,
        issued_on=parse_date(_first_text(root, ISSUED_TAGS)),
        total_cents=total,
        tax_cents=tax,
        amount_cents=amount,
        seller_name=_first_text(root, SELLER_NAME_TAGS),
        seller_tax_id=seller_tax_id,
        buyer_name=_first_text(root, BUYER_NAME_TAGS),
        buyer_tax_id=_first_text(root, BUYER_ID_TAGS),
        item_summary=summary,
        tax_category=category,
        invoice_type=_invoice_type(root),
        parser=parser_name,
        warnings=tuple(amount_warnings(total, amount, tax, upper)),
        raw_text=raw_text,
        region_code=region_code,
        region_name=region_name,
        order_no=find_order_no(raw_text),
    )


def _read_limited(path: Path) -> bytes | None:
    try:
        if path.stat().st_size > MAX_XML_BYTES:
            return None
        return path.read_bytes()
    except OSError as exc:
        logger.debug("无法读取 XML %s：%s", path, exc)
        return None


class XmlInvoiceParser:
    name = "xml_invoice"

    def can_parse(self, path: Path, text: str | None) -> bool:
        if text is not None:
            return looks_like_invoice_xml(text.encode("utf-8"))
        data = _read_limited(path)
        return data is not None and looks_like_invoice_xml(data)

    def parse(self, path: Path, text: str | None) -> ParsedInvoice:
        data = text.encode("utf-8") if text is not None else _read_limited(path)
        if data is None:
            raise InvoiceParseError(f"无法读取 XML：{path}")
        return parse_xml_bytes(data, parser_name=self.name)
