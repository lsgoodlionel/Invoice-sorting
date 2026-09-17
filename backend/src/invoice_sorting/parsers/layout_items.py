"""按坐标提取项目明细：用表头“项目名称”与其右侧最近列头的 x 坐标界定项目名称列。

- 表头下方、“合 计”行上方的区域为明细区；
- 名称列内的词按行聚类，以 *分类* 开头的行开始一个新项目，后续行（折行）拼接到该项目；
- 项目首行中位于名称列右侧的词作为数量/单价/金额等单元格，用于判定折扣行。
"""

import re
from collections.abc import Sequence

from invoice_sorting.parsers.items import (
    ITEM_START_RE,
    InvoiceItem,
    join_wrapped_lines,
    make_items,
)
from invoice_sorting.parsers.layout import LINE_TOLERANCE, PageWords, Word, group_lines, join_words

NAME_HEADER_RE = re.compile(r"^(?:项目名称|货物或应税劳务、?服务名称)$")
TOTAL_ROW_RE = re.compile(r"^(?:合|合计|价税合计.*)$")
HEADER_ROW_TOLERANCE = 3.0
COLUMN_TOLERANCE = 2.0  # 右侧列内容可能比列头略微左凸出


def _find_header(words: Sequence[Word]) -> Word | None:
    return next((w for w in words if NAME_HEADER_RE.match(w.text)), None)


def _name_column_right(header: Word, words: Sequence[Word]) -> float | None:
    same_row = [
        w.x0 for w in words if abs(w.top - header.top) <= HEADER_ROW_TOLERANCE and w.x0 >= header.x1
    ]
    return min(same_row) - COLUMN_TOLERANCE if same_row else None


def _body_bottom(header: Word, words: Sequence[Word], right: float) -> float:
    totals = [
        w.top
        for w in words
        if w.top > header.bottom and w.x0 < right and TOTAL_ROW_RE.match(w.text)
    ]
    return min(totals, default=float("inf"))


def _item_blocks(name_words: Sequence[Word]) -> list[list[list[Word]]]:
    """把名称列的行按“*分类*”开头切分为项目块；首个项目之前的零散行丢弃。"""
    blocks: list[list[list[Word]]] = []
    for line in group_lines(name_words):
        if ITEM_START_RE.match(line[0].text):
            blocks.append([line])
        elif blocks:
            blocks[-1] = [*blocks[-1], line]
    return blocks


def _row_cells(first_line: Sequence[Word], cell_words: Sequence[Word]) -> list[str]:
    top = first_line[0].top
    return [w.text for w in cell_words if abs(w.top - top) <= LINE_TOLERANCE]


def items_from_page(page: PageWords) -> list[InvoiceItem] | None:
    """无表头、无法界定名称列或未找到项目时返回 None，交由文本兜底。"""
    header = _find_header(page.words)
    right = _name_column_right(header, page.words) if header else None
    if header is None or right is None:
        return None
    bottom = _body_bottom(header, page.words, right)
    middle_of_header = (header.top + header.bottom) / 2
    body = [w for w in page.words if middle_of_header < w.top < bottom]
    name_words = [w for w in body if w.x0 < right]
    cell_words = [w for w in body if w.x0 >= right]
    rows = [
        (join_wrapped_lines([join_words(line) for line in block]), _row_cells(block[0], cell_words))
        for block in _item_blocks(name_words)
    ]
    return make_items(rows) or None
