"""按坐标提取购销方：左半页为购买方、右半页为销售方；同栏上下排列（旧版增值税票）时按先后。

标签在各半页内逐行匹配：把一行的词无空格拼接后查找“名称”/“统一社会信用代码/纳税人识别号”，
取标签右侧同一行、同一半页的词作为取值（半页边界即另一侧标签所在区域，天然截止）。
标签的字间空格、全/半角冒号、冒号与“/”落在下一行都不影响匹配。
"""

import re
from collections.abc import Sequence
from dataclasses import replace

from invoice_sorting.parsers.layout import PageWords, Word, group_lines, join_words
from invoice_sorting.parsers.parties import (
    NAME_LABEL_RE,
    TAX_ID_LABEL_RE,
    Parties,
    pair_or_empty,
    tax_id_after_label,
)
from invoice_sorting.parsers.text_utils import to_halfwidth

VALUE_NOISE_RE = re.compile(r"^[\s:：/]+|[\s:：/]+$")


def _words_after(line: Sequence[Word], end: int) -> list[Word]:
    """返回拼接串中位置 end 之后的词（跨越 end 的词只保留右侧部分）。"""
    result: list[Word] = []
    consumed = 0
    for current in line:
        start, consumed = consumed, consumed + len(current.text)
        if consumed <= end:
            continue
        cut = max(0, end - start)
        result.append(replace(current, text=current.text[cut:]) if cut else current)
    return result


def _label_values(lines: Sequence[Sequence[Word]], label: re.Pattern[str]) -> list[str]:
    """每个匹配到标签的行给出一个取值（可能为空串），按从上到下顺序。"""
    values: list[str] = []
    for line in lines:
        joined = to_halfwidth("".join(w.text for w in line))
        match = label.search(joined)
        if match:
            values.append(join_words(_words_after(line, match.end())))
    return values


def _half_values(lines: Sequence[Sequence[Word]]) -> tuple[list[str], list[str]]:
    names = [VALUE_NOISE_RE.sub("", value) for value in _label_values(lines, NAME_LABEL_RE)]
    ids = [tax_id_after_label(to_halfwidth(v)) for v in _label_values(lines, TAX_ID_LABEL_RE)]
    return names, ids


def _first(values: list[str]) -> str:
    return values[0] if values else ""


def parties_from_page(page: PageWords) -> Parties | None:
    """找不到销售方名称时返回 None，交由文本兜底。"""
    middle = page.width / 2
    left = group_lines(w for w in page.words if w.center < middle)
    right = group_lines(w for w in page.words if w.center >= middle)
    left_names, left_ids = _half_values(left)
    right_names, right_ids = _half_values(right)
    if right_names:
        buyer, seller = _first(left_names), _first(right_names)
        buyer_id, seller_id = _first(left_ids), _first(right_ids)
    else:
        buyer, seller = pair_or_empty(left_names)
        buyer_id, seller_id = pair_or_empty(left_ids)
    if not seller:
        return None
    return Parties(buyer, buyer_id, seller, seller_id)
