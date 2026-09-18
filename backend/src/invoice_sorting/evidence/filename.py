"""文件名线索：类型词、分类词、金额、日期、地区与文件名键（设计 3.3）。"""

import re
from datetime import date

from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.common.money import yuan_to_cents
from invoice_sorting.evidence.base import FilenameHints
from invoice_sorting.evidence.parsing import normalize
from invoice_sorting.parsers.regions import PROVINCES

MIN_KEY_CHARS = 4
MAX_AMOUNT_DIGITS = 7
DATE_DIGITS = 8
YEAR_MONTH_DIGITS = 6
MIN_YEAR, MAX_YEAR = 1990, 2099

TYPE_WORDS: dict[str, AttachmentKind] = {
    "电子发票": AttachmentKind.INVOICE,
    "普通发票": AttachmentKind.INVOICE,
    "专用发票": AttachmentKind.INVOICE,
    "发票": AttachmentKind.INVOICE,
    "交易订单": AttachmentKind.ORDER,
    "酒店订单": AttachmentKind.ORDER,
    "住宿订单": AttachmentKind.ORDER,
    "订单确认": AttachmentKind.ORDER,
    "预订确认": AttachmentKind.ORDER,
    "bookingconfirmation": AttachmentKind.ORDER,
    "订单详情": AttachmentKind.ORDER,
    "订单": AttachmentKind.ORDER,
    "收据": AttachmentKind.ORDER,
    "账单": AttachmentKind.ORDER,
    "receipt": AttachmentKind.ORDER,
    "invoice": AttachmentKind.ORDER,
    "银行交易": AttachmentKind.PAYMENT,
    "交易记录": AttachmentKind.PAYMENT,
    "交易明细": AttachmentKind.PAYMENT,
    "支付记录": AttachmentKind.PAYMENT,
    "付款记录": AttachmentKind.PAYMENT,
    "微信支付": AttachmentKind.PAYMENT,
    "支付宝": AttachmentKind.PAYMENT,
    "账单详情": AttachmentKind.PAYMENT,
    "电子行程单": AttachmentKind.ITINERARY,
    "行程单": AttachmentKind.ITINERARY,
    # 往来交通凭证：车票、机票等订单截图（发票类文件名仍以“发票”结尾时按发票处理）；
    # “行程单/行程”保持行程单，避免把网约车行程单误判为往来交通凭证
    "火车票": AttachmentKind.TRANSPORT,
    "高铁票": AttachmentKind.TRANSPORT,
    "高铁": AttachmentKind.TRANSPORT,
    "车票": AttachmentKind.TRANSPORT,
    "机票": AttachmentKind.TRANSPORT,
    "船票": AttachmentKind.TRANSPORT,
    "汽车票": AttachmentKind.TRANSPORT,
    "登机牌": AttachmentKind.TRANSPORT,
    "行程": AttachmentKind.ITINERARY,
    "验收单": AttachmentKind.ACCEPTANCE,
    "合同": AttachmentKind.CONTRACT,
    "协议": AttachmentKind.CONTRACT,
}
TYPE_WORD_RE = re.compile(
    "|".join(re.escape(word) for word in sorted(TYPE_WORDS, key=len, reverse=True))
)
EXTENSION_RE = re.compile(r"\.(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{2,5}$")
AMOUNT_SEGMENT_RE = re.compile(r"^(\d+)(\.\d{1,2})?元?$")
REGION_SEGMENT_RE = re.compile(
    "^(" + "|".join(PROVINCES.values()) + r")(省|市|(?:壮族|回族|维吾尔)?自治区)?$"
)
EDGE_PUNCTUATION = " 【】[]()<>《》「」'\"_.,+"


def _stem(original_name: str) -> str:
    name = normalize(original_name).strip()
    return EXTENSION_RE.sub("", name)


def _segments(stem: str) -> list[str]:
    return [segment.strip(EDGE_PUNCTUATION) for segment in stem.split("-")]


def _yyyymm(digits: str) -> bool:
    return MIN_YEAR <= int(digits[:4]) <= MAX_YEAR and 1 <= int(digits[4:]) <= 12


def _amount_cents(segment: str) -> int | None:
    match = AMOUNT_SEGMENT_RE.match(segment)
    if not match:
        return None
    integer, decimal = match.groups()
    if decimal is None:
        too_long = len(integer) > MAX_AMOUNT_DIGITS
        looks_like_date = len(integer) == YEAR_MONTH_DIGITS and _yyyymm(integer)
        if too_long or looks_like_date or integer.startswith("0"):
            return None
    return yuan_to_cents(integer + (decimal or ""))


def _segment_date(segment: str) -> date | None:
    if not segment.isdigit() or not segment.isascii():
        return None
    if len(segment) >= DATE_DIGITS and len(segment) <= DATE_DIGITS + 1:
        try:
            return date(int(segment[:4]), int(segment[4:6]), int(segment[6:8]))
        except ValueError:
            return None
    if len(segment) == YEAR_MONTH_DIGITS and _yyyymm(segment):
        return date(int(segment[:4]), int(segment[4:]), 1)
    return None


def _region(segment: str) -> str:
    match = REGION_SEGMENT_RE.match(segment)
    return match.group(1) if match else ""


def _kind(stem: str) -> str | None:
    matches = list(TYPE_WORD_RE.finditer(stem.lower()))
    return TYPE_WORDS[matches[-1].group(0)].value if matches else None


def _category_word(stem: str) -> str:
    if "-" not in stem:
        return ""
    word = stem.split("-", 1)[0].split("+", 1)[0].strip(EDGE_PUNCTUATION)
    return "" if word.isdigit() or TYPE_WORD_RE.fullmatch(word.lower()) else word


def _first[T](values: list[T | None]) -> T | None:
    return next((value for value in values if value is not None), None)


def file_key(original_name: str) -> str:
    """同一笔支出的文件名键；有效字符不足 4 个时返回 ""。"""
    stem = TYPE_WORD_RE.sub("", _stem(original_name).lower())
    parts: list[str] = []
    for segment in _segments(stem):
        if _amount_cents(segment) is not None or _region(segment):
            continue
        cleaned = "".join(char for char in segment if char.isalnum())
        if cleaned:
            parts.append(cleaned)
    key = "-".join(parts)
    return key if len(key) - key.count("-") >= MIN_KEY_CHARS else ""


def filename_hints(original_name: str) -> FilenameHints:
    stem = _stem(original_name)
    segments = _segments(TYPE_WORD_RE.sub("", stem.lower()))
    return FilenameHints(
        kind=_kind(stem),
        category_word=_category_word(stem),
        amount_cents=_first([_amount_cents(segment) for segment in segments]),
        occurred_on=_first([_segment_date(segment) for segment in segments]),
        region=next((region for region in map(_region, segments) if region), ""),
        file_key=file_key(original_name),
    )
