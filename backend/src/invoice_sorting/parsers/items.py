"""发票项目：折扣行判定、折行名称拼接、摘要生成与纯文本兜底提取。"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from invoice_sorting.parsers.text_utils import split_item_name

MAX_SUMMARY_NAME = 60
ELLIPSIS = "…"
ITEM_START_RE = re.compile(r"^\*[^*\s]+\*")
NUMBER_RE = re.compile(r"^-?\d[\d,]*(?:\.\d+)?$")
NEGATIVE_RE = re.compile(r"^-\d[\d,]*\.\d+$")
MAX_DISCOUNT_NUMBERS = 2  # 折扣行只有金额、税额两列数字（无数量、单价）


@dataclass(frozen=True)
class InvoiceItem:
    category: str  # *分类简称*，无则 ""
    name: str  # 去掉分类前缀后的完整名称
    is_discount: bool = False


def is_discount_row(cells: Sequence[str], name: str, previous_name: str | None) -> bool:
    """折扣行：有负数金额，且无数量/单价（数字列不超过 2 个）或与上一项同名。"""
    if not any(NEGATIVE_RE.match(cell) for cell in cells):
        return False
    numbers = sum(1 for cell in cells if NUMBER_RE.match(cell))
    return numbers <= MAX_DISCOUNT_NUMBERS or name == previous_name


def make_items(rows: Sequence[tuple[str, Sequence[str]]]) -> list[InvoiceItem]:
    """rows 为 (含分类前缀的名称, 该行其余单元格)。"""
    items: list[InvoiceItem] = []
    for raw_name, cells in rows:
        category, name = split_item_name(raw_name)
        previous = items[-1].name if items else None
        items.append(InvoiceItem(category, name, is_discount_row(cells, name, previous)))
    return items


def join_wrapped_lines(lines: Sequence[str]) -> str:
    """列内折行直接相连；仅当断点两侧都是 ASCII 字母数字时补一个空格（如 “DDR5 / 4800”）。"""
    text = ""
    for line in (part.strip() for part in lines):
        if not line:
            continue
        boundary = text[-1:] + line[:1]
        separator = " " if len(boundary) == 2 and boundary.isascii() and boundary.isalnum() else ""
        text = f"{text}{separator}{line}"
    return text


def _shorten(name: str) -> str:
    return name if len(name) <= MAX_SUMMARY_NAME else name[:MAX_SUMMARY_NAME] + ELLIPSIS


def summarize_invoice_items(items: Sequence[InvoiceItem]) -> tuple[str, str]:
    """返回 (item_summary, tax_category)：首个非折扣项目名称 + “等N项”（N 不含折扣行）。"""
    if not items:
        return "", ""
    regular = [item for item in items if not item.is_discount] or [items[0]]
    first = regular[0]
    summary = _shorten(first.name)
    if len(regular) > 1:
        summary = f"{summary}等{len(regular)}项"
    return summary, first.category


def summarize_items(names: Sequence[str]) -> tuple[str, str]:
    """仅有名称列表（如 XML）时的摘要：不做折扣判定。"""
    return summarize_invoice_items([make_items([(name, ())])[0] for name in names])


def items_from_text(text: str) -> list[InvoiceItem]:
    """无坐标时的兜底：以 *分类* 开头的行，名称取第一个空白前的片段，其余作为单元格。"""
    rows: list[tuple[str, Sequence[str]]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if ITEM_START_RE.match(stripped):
            name, *cells = stripped.split()
            rows.append((name, cells))
    return make_items(rows)
