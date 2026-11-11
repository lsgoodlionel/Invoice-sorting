"""复合凭证拆分：识别 Gmail 打印的 Apple 多回执 PDF。"""

import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

GMAIL_APPLE_MARKER = "your purchases from apple"
RECEIPT_LINE = re.compile(r"(?im)^\s*receipt\s*$")
ORDER_LABEL = re.compile(r"(?i)^\s*order\s*id\s*:?[ \t]*(.*)$")
ORDER_VALUE = re.compile(r"^[A-Z0-9][A-Z0-9-]+$")


class CompositeSplitError(ValueError):
    """复合凭证边界不明确，不能安全自动拆分。"""


@dataclass(frozen=True)
class CompositePart:
    order_no: str
    start_page: int
    end_page: int
    text: str


def _order_no(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        matched = ORDER_LABEL.match(line)
        if matched is None:
            continue
        inline = matched.group(1).strip().upper()
        if ORDER_VALUE.fullmatch(inline):
            return inline
        if index + 1 < len(lines):
            below = lines[index + 1].strip().upper()
            if ORDER_VALUE.fullmatch(below):
                return below
    return ""


def split_apple_gmail_pdf(path: Path) -> list[CompositePart]:
    """返回安全、有序的 Apple 回执页范围；非目标格式返回空列表。"""
    reader = PdfReader(path)
    page_texts = [(page.extract_text() or "").replace("\xa0", " ") for page in reader.pages]
    joined = "\n".join(page_texts)
    if GMAIL_APPLE_MARKER not in joined.lower():
        return []
    starts: list[int] = []
    for index, text in enumerate(page_texts):
        count = len(RECEIPT_LINE.findall(text))
        if count > 1:
            raise CompositeSplitError("同一页包含多张 Apple 回执，无法安全自动拆分")
        if count == 1:
            starts.append(index)
    if len(starts) < 2:
        return []
    parts: list[CompositePart] = []
    seen: set[str] = set()
    for position, start in enumerate(starts):
        end = starts[position + 1] - 1 if position + 1 < len(starts) else len(page_texts) - 1
        text = "\n".join(page_texts[start : end + 1])
        order_no = _order_no(text)
        if not order_no:
            raise CompositeSplitError(f"第 {start + 1} 页起的 Apple 回执缺少 Order ID")
        if order_no in seen:
            raise CompositeSplitError(f"Apple 回执 Order ID 重复：{order_no}")
        seen.add(order_no)
        parts.append(CompositePart(order_no, start + 1, end + 1, text))
    return parts
