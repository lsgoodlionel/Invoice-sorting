"""数电发票 / 增值税电子发票的纯文本字段提取（PDF 与 OFD 共用）。"""

import re

from invoice_sorting.parsers.base import ParsedInvoice
from invoice_sorting.parsers.cn_amount import CN_AMOUNT_CHARS, cn_upper_to_cents
from invoice_sorting.parsers.items import items_from_text, summarize_invoice_items
from invoice_sorting.parsers.layout import PageWords
from invoice_sorting.parsers.layout_items import items_from_page
from invoice_sorting.parsers.layout_parties import parties_from_page
from invoice_sorting.parsers.parties import Parties, extract_text_parties
from invoice_sorting.parsers.regions import region_from_invoice
from invoice_sorting.parsers.text_utils import (
    AMOUNT,
    compact,
    find_invoice_code,
    find_invoice_no,
    find_labeled_date,
    find_order_no,
    normalize_text,
    search_group,
    to_cents,
)

SUBTOTAL_RE = re.compile(
    r"^合\s*计\s*¥?\s*(" + AMOUNT + r")\s*¥?\s*(" + AMOUNT + r"|\*+)", re.MULTILINE
)
LOWER_TOTAL_RE = re.compile(r"小\s*写\s*\)?\s*¥?\s*(" + AMOUNT + ")")
UPPER_TOTAL_RE = re.compile(
    r"大\s*写\s*\)?\s*[^" + CN_AMOUNT_CHARS + r"\n]{0,4}([" + CN_AMOUNT_CHARS + r"]+)"
)

TYPE_RULES: tuple[tuple[str, str], ...] = (
    ("电子发票(增值税专用发票)", "数电发票（增值税专用发票）"),
    ("电子发票(普通发票)", "数电发票（普通发票）"),
    ("增值税电子专用发票", "增值税电子专用发票"),
    ("增值税电子普通发票", "增值税电子普通发票"),
    ("增值税专用发票", "增值税专用发票"),
    ("增值税普通发票", "增值税普通发票"),
)
SUM_MISMATCH = "价税合计与金额+税额不一致"
UPPER_MISMATCH = "大小写金额不一致"


def extract_parties(text: str, page: PageWords | None = None) -> Parties:
    """首选坐标（左购右销，或同栏上购下销），失败时按文本阅读顺序兜底。"""
    from_page = parties_from_page(page) if page is not None else None
    return from_page if from_page is not None else extract_text_parties(text)


def extract_summary(text: str, page: PageWords | None = None) -> tuple[str, str]:
    """首选坐标界定的项目名称列（完整折行名称），失败时按文本行兜底。"""
    items = items_from_page(page) if page is not None else None
    return summarize_invoice_items(items if items is not None else items_from_text(text))


def detect_invoice_type(text: str, invoice_no: str | None) -> str:
    flat = compact(text)
    for keyword, label in TYPE_RULES:
        if keyword in flat:
            return label
    if invoice_no and len(invoice_no) == 20:
        return "数电发票"
    return ""


def _subtotals(text: str) -> tuple[int | None, int | None]:
    match = SUBTOTAL_RE.search(text)
    if not match:
        return None, None
    tax_text = match.group(2)
    tax = 0 if tax_text.startswith("*") else to_cents(tax_text)
    return to_cents(match.group(1)), tax


def amount_warnings(
    total: int | None, amount: int | None, tax: int | None, upper: int | None = None
) -> list[str]:
    warnings: list[str] = []
    if total is None:
        warnings.append("未识别到价税合计")
    elif amount is not None and tax is not None and amount + tax != total:
        warnings.append(SUM_MISMATCH)
    if total is not None and upper is not None and upper != total:
        warnings.append(UPPER_MISMATCH)
    return warnings


def _full_invoice_no(text: str) -> str | None:
    number = find_invoice_no(text)
    code = find_invoice_code(text)
    if number and code and len(number) <= 8:
        return f"{code}-{number}"
    return number


def _warnings(text: str, invoice_no: str | None) -> list[str]:
    amount, tax = _subtotals(text)
    total = to_cents(search_group(LOWER_TOTAL_RE.pattern, text))
    upper_text = search_group(UPPER_TOTAL_RE.pattern, text)
    upper = cn_upper_to_cents(upper_text) if upper_text else None
    warnings = amount_warnings(total, amount, tax, upper)
    if upper_text and upper is None:
        warnings.append("大写金额无法解析")
    if invoice_no is None:
        warnings.append("未识别到发票号码")
    return warnings


def parse_invoice_text(
    raw_text: str, parser_name: str, page: PageWords | None = None
) -> ParsedInvoice:
    text = normalize_text(raw_text)
    invoice_no = _full_invoice_no(text)
    amount, tax = _subtotals(text)
    parties = extract_parties(raw_text, page)
    summary, category = extract_summary(text, page)
    region_code, region_name = region_from_invoice(invoice_no, parties.seller_tax_id)
    return ParsedInvoice(
        invoice_no=invoice_no,
        issued_on=find_labeled_date(("开票日期",), text),
        total_cents=to_cents(search_group(LOWER_TOTAL_RE.pattern, text)),
        tax_cents=tax,
        amount_cents=amount,
        seller_name=parties.seller_name,
        seller_tax_id=parties.seller_tax_id,
        buyer_name=parties.buyer_name,
        buyer_tax_id=parties.buyer_tax_id,
        item_summary=summary,
        tax_category=category,
        invoice_type=detect_invoice_type(text, invoice_no),
        parser=parser_name,
        warnings=tuple(_warnings(text, invoice_no)),
        raw_text=raw_text,
        region_code=region_code,
        region_name=region_name,
        order_no=find_order_no(text),
    )


def looks_like_vat_invoice(text: str) -> bool:
    flat = compact(text)
    return "发票号码" in flat and "价税合计" in flat
