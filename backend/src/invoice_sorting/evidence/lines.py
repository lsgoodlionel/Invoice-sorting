"""识别器统一输入：带坐标的文本框按行组织（OCR 或 PDF 文本层）。"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from statistics import mean

from invoice_sorting.evidence.parsing import normalize

ROW_TOLERANCE = 0.5  # 行聚类：y 中心差 ≤ 框高 × 该比例视为同一行
SYNTHETIC_CELL_WIDTH = 500  # 构造行（无坐标）时每个单元格的虚拟宽度


@dataclass(frozen=True)
class TextBox:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def y_center(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def height(self) -> float:
        return max(self.y1 - self.y0, 1.0)


@dataclass(frozen=True)
class TextLine:
    boxes: tuple[TextBox, ...]

    @property
    def text(self) -> str:
        return " ".join(box.text for box in self.boxes)


@dataclass(frozen=True)
class EvidenceText:
    lines: tuple[TextLine, ...] = ()

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def compact(self) -> str:
        """去空白、转小写，用于特征词判断。"""
        return re.sub(r"\s+", "", self.text).lower()


def _clean_box(box: TextBox) -> TextBox | None:
    text = normalize(box.text).strip()
    return TextBox(text, box.x0, box.y0, box.x1, box.y1) if text else None


def _group_rows(boxes: list[TextBox]) -> list[list[TextBox]]:
    rows: list[list[TextBox]] = []
    for box in sorted(boxes, key=lambda item: item.y_center):
        if rows:
            row = rows[-1]
            center = mean(item.y_center for item in row)
            height = min(box.height, mean(item.height for item in row))
            if abs(box.y_center - center) <= height * ROW_TOLERANCE:
                row.append(box)
                continue
        rows.append([box])
    return rows


def lines_from_boxes(boxes: Iterable[TextBox]) -> tuple[TextLine, ...]:
    """按 y 中心聚类为行，行内按 x 排序；空文本框丢弃。"""
    cleaned = [box for box in map(_clean_box, boxes) if box is not None]
    rows = _group_rows(cleaned)
    return tuple(TextLine(tuple(sorted(row, key=lambda item: item.x0))) for row in rows)


def doc_from_rows(rows: Sequence[Sequence[str]]) -> EvidenceText:
    """由“行 → 单元格文本”构造文档，单元格按列分配虚拟坐标（测试与纯文本来源使用）。"""
    boxes = [
        TextBox(
            cell,
            col * SYNTHETIC_CELL_WIDTH,
            row * 10,
            (col + 1) * SYNTHETIC_CELL_WIDTH - 1,
            row * 10 + 8,
        )
        for row, cells in enumerate(rows)
        for col, cell in enumerate(cells)
    ]
    return EvidenceText(lines_from_boxes(boxes))


def lines_from_text(text: str) -> EvidenceText:
    """纯文本（PDF 文本层）：每个非空行为一个文本框。"""
    return doc_from_rows([[line] for line in text.splitlines() if line.strip()])


def find_line(doc: EvidenceText, pattern: str, start: int = 0) -> int:
    """返回首个匹配 pattern 的行号，无则 -1。"""
    regex = re.compile(pattern, re.IGNORECASE)
    for index, line in enumerate(doc.lines[start:], start=start):
        if regex.search(line.text):
            return index
    return -1


def value_after(doc: EvidenceText, label: str) -> str:
    """同一行中标签右侧的文本（标签在左、值在右的布局）。"""
    regex = re.compile(label, re.IGNORECASE)
    for line in doc.lines:
        match = regex.search(line.text)
        if match:
            value = line.text[match.end() :].strip(" :")
            if value:
                return value
    return ""


def _overlap(left: TextBox, right: TextBox) -> float:
    return min(left.x1, right.x1) - max(left.x0, right.x0)


def value_below(doc: EvidenceText, label: str) -> str:
    """标签框下一行中与其水平重叠最多的文本框（标签在上、值在下的布局）。"""
    regex = re.compile(label, re.IGNORECASE)
    for index, line in enumerate(doc.lines[:-1]):
        for box in line.boxes:
            if not regex.search(box.text):
                continue
            below = max(doc.lines[index + 1].boxes, key=lambda item: _overlap(box, item))
            if _overlap(box, below) > 0:
                return below.text
    return ""
