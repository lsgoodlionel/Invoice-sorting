"""商家名相似度与“商家词有交集”判断（分组 L3 与匹配 M3 共用）。"""

import re

from invoice_sorting.importer.platforms import platforms_compatible

CONTAINMENT_BONUS = 1000
MIN_COMMON_CHARS = 2
COMPANY_SUFFIXES = re.compile(r"(股份有限公司|有限责任公司|有限公司|公司|商行|店)$")
WHITESPACE = re.compile(r"\s+")


def _normalize_merchant(name: str) -> str:
    text = WHITESPACE.sub("", name or "").lower()
    return COMPANY_SUFFIXES.sub("", text)


def _longest_common_substring(first: str, second: str) -> int:
    best = 0
    previous = [0] * (len(second) + 1)
    for char in first:
        current = [0] * (len(second) + 1)
        for index, other in enumerate(second, start=1):
            if char == other:
                current[index] = previous[index - 1] + 1
                best = max(best, current[index])
        previous = current
    return best


def merchant_similarity(first: str, second: str) -> int:
    """包含关系得分最高（加上较短名称长度），否则为最长公共子串长度。"""
    left, right = _normalize_merchant(first), _normalize_merchant(second)
    if not left or not right:
        return 0
    if left in right or right in left:
        return CONTAINMENT_BONUS + min(len(left), len(right))
    return _longest_common_substring(left, right)


def merchants_overlap(
    first: str, first_platforms: frozenset[str], second: str, second_platforms: frozenset[str]
) -> bool:
    """商家名有至少 2 个连续相同字符，或平台兼容。"""
    if merchant_similarity(first, second) >= MIN_COMMON_CHARS:
        return True
    return platforms_compatible(first_platforms, second_platforms)
