"""解析器共享的文本规范化、正则与小工具。"""

import re
from datetime import date

from invoice_sorting.common.money import yuan_to_cents

INVOICE_KEYWORDS: tuple[str, ...] = ("发票号码", "电子发票", "电子客票", "行程单", "发票代码")

_TRANSLATION = str.maketrans(
    {
        "（": "(",
        "）": ")",
        "：": ":",
        "￥": "¥",
        "　": " ",
        "\xa0": " ",
    }
)

AMOUNT = r"-?\d[\d,]*\.\d{1,2}"
CHINESE_WORD = r"[一-鿿][一-鿿A-Za-z0-9()·]*"


def to_halfwidth(text: str) -> str:
    """全角标点转半角（逐字符替换，长度不变）。"""
    return text.translate(_TRANSLATION)


def normalize_text(text: str) -> str:
    """全角标点转半角、统一人民币符号，逐行去掉首尾空白。"""
    lines = (line.strip() for line in text.translate(_TRANSLATION).splitlines())
    return "\n".join(lines)


def compact(text: str) -> str:
    """去掉所有空白，便于关键字判断（pdf 常把“发 票 号 码”拆开）。"""
    return re.sub(r"\s+", "", text.translate(_TRANSLATION))


def spaced(label: str) -> str:
    """把标签转为允许字间空白的正则片段，如 “发票号码” → “发\\s*票\\s*号\\s*码”。"""
    return r"\s*".join(re.escape(char) for char in label)


def labeled(label: str) -> str:
    """标签 + 可选冒号的正则片段。"""
    return spaced(label) + r"\s*:?\s*"


def contains_invoice_keyword(text: str) -> bool:
    flat = compact(text)
    return any(keyword in flat for keyword in INVOICE_KEYWORDS)


def search_group(pattern: str, text: str, flags: int = 0) -> str | None:
    match = re.search(pattern, text, flags)
    return match.group(1).strip() if match else None


def to_cents(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return yuan_to_cents(value)
    except ValueError:
        return None


def make_date(year: str, month: str, day: str) -> date | None:
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


DATE_PATTERN = r"(\d{4})\s*(?:年|-|/|\.)\s*(\d{1,2})\s*(?:月|-|/|\.)\s*(\d{1,2})\s*日?"


def parse_date(text: str | None) -> date | None:
    """解析“2026年09月15日”“2026-09-15”“2026-09-15 10:00:00”等格式。"""
    if not text:
        return None
    match = re.search(DATE_PATTERN, text)
    return make_date(*match.groups()) if match else None


def find_labeled_date(labels: tuple[str, ...], text: str) -> date | None:
    for label in labels:
        match = re.search(labeled(label) + DATE_PATTERN, text)
        if match:
            return make_date(*match.groups())
    return None


def find_invoice_no(text: str) -> str | None:
    return search_group(labeled("发票号码") + r"(\d{8,20})", text)


def find_invoice_code(text: str) -> str | None:
    return search_group(labeled("发票代码") + r"(\d{10,12})", text)


ORDER_NO_RE = re.compile(r"订\s*单\s*(?:编\s*)?号\s*[:：]\s*([0-9A-Za-z-]+)")


def find_order_no(text: str) -> str:
    """提取备注中的电商订单号（“订单号:xxx”或“订单编号：xxx”），无则 ""。"""
    match = ORDER_NO_RE.search(text)
    return match.group(1) if match else ""


def find_labeled_name(labels: tuple[str, ...], text: str) -> str:
    for label in labels:
        value = search_group(labeled(label) + r"(" + CHINESE_WORD + r")", text)
        if value:
            return value
    return ""


def find_labeled_tax_id(labels: tuple[str, ...], text: str) -> str:
    for label in labels:
        value = search_group(labeled(label) + r"([0-9A-Z]{15,20})\b", text)
        if value:
            return value
    return ""


def split_item_name(raw_name: str) -> tuple[str, str]:
    """“*计算机配套产品*鼠标” → (“计算机配套产品”, “鼠标”)；无分类前缀时分类为空。"""
    match = re.match(r"\s*\*([^*]+)\*\s*(.*)", raw_name)
    if not match:
        return "", raw_name.strip()
    return match.group(1).strip(), match.group(2).strip()
