"""复合 PDF 拆成可沿用普通导入流程的子 PDF。"""

from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from invoice_sorting.db.models import SourceDocument
from invoice_sorting.evidence.composite import CompositePart

APPLE_SPLITTER = "apple_gmail_v1"


@dataclass(frozen=True)
class PreparedChild:
    path: Path
    name: str
    source: SourceDocument
    part: CompositePart


def prepare_apple_children(
    src: Path, source: SourceDocument, parts: list[CompositePart], temp: Path
) -> list[PreparedChild]:
    reader = PdfReader(src)
    children: list[PreparedChild] = []
    for part in parts:
        writer = PdfWriter()
        for page_index in range(part.start_page - 1, part.end_page):
            writer.add_page(reader.pages[page_index])
        path = temp / f"Apple_{part.order_no}.pdf"
        with path.open("wb") as handle:
            writer.write(handle)
        children.append(PreparedChild(path, path.name, source, part))
    return children
