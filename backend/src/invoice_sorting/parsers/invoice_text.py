"""数电发票 / 增值税电子发票的纯文本字段提取（PDF 与 OFD 共用）。"""

import re
from dataclasses import dataclass

from invoice_sorting.parsers.base import ParsedInvoice
from invoice_sorting.parsers.cn_amount import CN_AMOUNT_CHARS, cn_upper_to_cents
from invoice_sorting.parsers.pdf_text import PdfColumns
from invoice_sorting.parsers.text_utils import (
    AMOUNT,
    compact,
    find_invoice_code,
    find_invoice_no,
    find_labeled_date,
    normalize_text,
    search_group,
    summarize_items,
    to_cents,
)

NAME_LABEL_RE = re.compile(r"名\s*称\s*:\s*")
TAX_ID_LABEL = (
    r"(?:统\s*一\s*社\s*会\s*信\s*用\s*代\s*码(?:\s*/\s*纳\s*税\s*人\s*识\s*别\s*号)?"
    r"|纳\s*税\s*人\s*识\s*别\s*号)\s*:?\s*([0-9A-Z]{15,20})?"
)
TAX_ID_RE = re.compile(TAX_ID_LABEL)
PARTY_NOISE_RE = re.compile(r"(?:\s+[购买销售方信息])+$")
ITEM_LINE_RE = re.compile(r"^\*[^*\s]+\*\S+", re.MULTILINE)
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


@dataclass(frozen=True)
class Parties:
    buyer_name: str
    buyer_tax_id: str
    seller_name: str
    seller_tax_id: str


def _clean_party_name(value: str) -> str:
    """去掉竖排标签残字（如“销”“售”），并截断到第一个空白（右侧可能并排了其他栏内容）。"""
    tokens = PARTY_NOISE_RE.sub("", " " + value.strip()).split()
    return tokens[0] if tokens else ""


def party_names(text: str) -> list[str]:
    """按阅读顺序列出所有“名称：”取值（保留空值占位，便于区分左右）。"""
    names: list[str] = []
    for line in normalize_text(text).splitlines():
        segments = NAME_LABEL_RE.split(line)
        names.extend(_clean_party_name(segment) for segment in segments[1:])
    return names


def party_tax_ids(text: str) -> list[str]:
    return [match.group(1) or "" for match in TAX_ID_RE.finditer(normalize_text(text))]


def _first(values: list[str]) -> str:
    return values[0] if values else ""


def _pair_or_empty(values: list[str]) -> tuple[str, str]:
    padded = [*values, "", ""]
    return padded[0], padded[1]


def _pair_from_columns(left: list[str], right: list[str], side_by_side: bool) -> tuple[str, str]:
    return (_first(left), _first(right)) if side_by_side else _pair_or_empty(left)


def _parties_from_columns(columns: PdfColumns) -> Parties | None:
    left_names, right_names = party_names(columns.left), party_names(columns.right)
    side_by_side = bool(right_names)
    buyer, seller = _pair_from_columns(left_names, right_names, side_by_side)
    if not seller:
        return None
    ids = _pair_from_columns(
        party_tax_ids(columns.left), party_tax_ids(columns.right), side_by_side
    )
    return Parties(buyer, ids[0], seller, ids[1])


def extract_parties(text: str, columns: PdfColumns | None = None) -> Parties:
    """首选坐标分栏（左购右销，或同栏上购下销），失败时按文本阅读顺序兜底。"""
    from_columns = _parties_from_columns(columns) if columns is not None else None
    if from_columns is not None:
        return from_columns
    buyer, seller = _pair_or_empty(party_names(text))
    buyer_id, seller_id = _pair_or_empty(party_tax_ids(text))
    return Parties(buyer, buyer_id, seller, seller_id)


def detect_invoice_type(text: str, invoice_no: str | None) -> str:
    flat = compact(text)
    for keyword, label in TYPE_RULES:
        if keyword in flat:
            return label
    if invoice_no and len(invoice_no) == 20:
        return "数电发票"
    return ""


def _item_names(text: str) -> list[str]:
    return [match.group(0) for match in ITEM_LINE_RE.finditer(text)]


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


def parse_invoice_text(
    raw_text: str, parser_name: str, columns: PdfColumns | None = None
) -> ParsedInvoice:
    text = normalize_text(raw_text)
    invoice_no = _full_invoice_no(text)
    amount, tax = _subtotals(text)
    total = to_cents(search_group(LOWER_TOTAL_RE.pattern, text))
    upper_text = search_group(UPPER_TOTAL_RE.pattern, text)
    upper = cn_upper_to_cents(upper_text) if upper_text else None
    warnings = amount_warnings(total, amount, tax, upper)
    if upper_text and upper is None:
        warnings.append("大写金额无法解析")
    if invoice_no is None:
        warnings.append("未识别到发票号码")
    parties = extract_parties(raw_text, columns)
    summary, category = summarize_items(_item_names(text))
    return ParsedInvoice(
        invoice_no=invoice_no,
        issued_on=find_labeled_date(("开票日期",), text),
        total_cents=total,
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
        warnings=tuple(warnings),
        raw_text=raw_text,
    )


def looks_like_vat_invoice(text: str) -> bool:
    flat = compact(text)
    return "发票号码" in flat and "价税合计" in flat
