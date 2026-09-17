"""版式坐标的基础结构：词、页面、按行聚类与带空格语义的拼接（不依赖 pdfplumber）。"""

from collections.abc import Iterable
from dataclasses import dataclass

LINE_TOLERANCE = 2.0  # 同一行的 top 允许差（pt）
TOUCH_GAP = 0.5  # 词间距不超过此值视为同一个词被拆开（如小字号折行交错）
CJK_PUNCTUATION = frozenset("（）【】《》「」『』、，。：；！？“”‘’·…—")


@dataclass(frozen=True)
class Word:
    x0: float
    x1: float
    top: float
    bottom: float
    text: str

    @property
    def center(self) -> float:
        return (self.x0 + self.x1) / 2


@dataclass(frozen=True)
class PageWords:
    """首页所有词（pdfplumber 坐标：原点左上，top 向下增大）。"""

    width: float
    words: tuple[Word, ...]


def is_cjk(char: str) -> bool:
    return "一" <= char <= "鿿" or char in CJK_PUNCTUATION


def needs_space(left: str, right: str) -> bool:
    """中文与中文之间不留空格，其余（中英、英英）保留一个空格。"""
    if not left or not right:
        return False
    return not (is_cjk(left[-1]) and is_cjk(right[0]))


def join_words(words: Iterable[Word]) -> str:
    """同一行的词按 x 排序后拼接：紧贴的词直接相连，否则按中英文规则决定是否留空格。"""
    text = ""
    previous: Word | None = None
    for current in sorted(words, key=lambda w: w.x0):
        touching = previous is not None and current.x0 - previous.x1 <= TOUCH_GAP
        separator = " " if previous and not touching and needs_space(text, current.text) else ""
        text = f"{text}{separator}{current.text}"
        previous = current
    return text


def group_lines(words: Iterable[Word], tolerance: float = LINE_TOLERANCE) -> list[list[Word]]:
    """按 top 聚类成行（行首词 top 为基准），行内按 x 排序。"""
    lines: list[list[Word]] = []
    for current in sorted(words, key=lambda w: (w.top, w.x0)):
        if lines and current.top - lines[-1][0].top <= tolerance:
            lines[-1] = [*lines[-1], current]
        else:
            lines.append([current])
    return [sorted(line, key=lambda w: w.x0) for line in lines]
