"""OFD 版式发票解析器：优先读取包内发票 XML，否则拼接页面 TextCode 走文本兜底。"""

import logging
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from invoice_sorting.parsers.base import InvoiceParseError, ParsedInvoice
from invoice_sorting.parsers.invoice_text import looks_like_vat_invoice, parse_invoice_text
from invoice_sorting.parsers.xml_invoice import (
    FORBIDDEN_DTD,
    local_name,
    looks_like_invoice_xml,
    parse_xml_bytes,
)

logger = logging.getLogger(__name__)

MAX_ENTRIES = 500
MAX_ENTRY_BYTES = 5 * 1024 * 1024
LINE_TOLERANCE = 1.5
CONTENT_RE = re.compile(r"(?:^|/)Pages/Page_?\d+/Content\.xml$", re.IGNORECASE)


def _safe_entries(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    entries = archive.infolist()
    if len(entries) > MAX_ENTRIES:
        raise InvoiceParseError("OFD 包内文件过多")
    return [entry for entry in entries if entry.file_size <= MAX_ENTRY_BYTES]


def invoice_xml_candidates(archive: zipfile.ZipFile) -> list[bytes]:
    entries = [e for e in _safe_entries(archive) if e.filename.lower().endswith(".xml")]
    entries.sort(key=lambda entry: "attachs/" not in entry.filename.lower())
    candidates = []
    for entry in entries:
        if CONTENT_RE.search(entry.filename):
            continue
        data = archive.read(entry)
        if looks_like_invoice_xml(data):
            candidates.append(data)
    return candidates


def _float(value: str | None, index: int = 0) -> float:
    try:
        return float((value or "").split()[index])
    except (IndexError, ValueError):
        return 0.0


def _page_text_objects(data: bytes) -> list[tuple[float, float, str]]:
    if FORBIDDEN_DTD.search(data):
        return []
    objects = []
    for element in ET.fromstring(data).iter():
        if local_name(element.tag) != "textobject":
            continue
        boundary = element.get("Boundary")
        for code in element:
            if local_name(code.tag) == "textcode" and code.text:
                y = _float(boundary, 1) + _float(code.get("Y"))
                x = _float(boundary, 0) + _float(code.get("X"))
                objects.append((y, x, code.text))
    return objects


def _join_lines(objects: list[tuple[float, float, str]]) -> str:
    lines: list[list[tuple[float, float, str]]] = []
    for obj in sorted(objects):
        if lines and abs(lines[-1][0][0] - obj[0]) <= LINE_TOLERANCE:
            lines[-1].append(obj)
        else:
            lines.append([obj])
    return "\n".join(
        " ".join(text for _, _, text in sorted(line, key=lambda o: o[1])) for line in lines
    )


def ofd_text(archive: zipfile.ZipFile) -> str:
    """OFD 坐标 y 轴向下，按 (y, x) 排序拼出近似阅读顺序的文本。"""
    pages = sorted(e.filename for e in _safe_entries(archive) if CONTENT_RE.search(e.filename))
    return "\n".join(_join_lines(_page_text_objects(archive.read(name))) for name in pages)


def _is_ofd_zip(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            return any(name.lower().endswith("ofd.xml") for name in archive.namelist())
    except (OSError, zipfile.BadZipFile) as exc:
        logger.debug("不是有效的 OFD 包 %s：%r", path, exc)
        return False


class OfdInvoiceParser:
    name = "ofd_invoice"

    def can_parse(self, path: Path, text: str | None) -> bool:
        return path.suffix.lower() == ".ofd" or _is_ofd_zip(path)

    def parse(self, path: Path, text: str | None) -> ParsedInvoice:
        try:
            with zipfile.ZipFile(path) as archive:
                for data in invoice_xml_candidates(archive):
                    try:
                        return parse_xml_bytes(data, parser_name=self.name)
                    except InvoiceParseError as exc:
                        logger.debug("OFD 内 XML 不是发票：%s", exc)
                content = text or ofd_text(archive)
        except (OSError, zipfile.BadZipFile, ET.ParseError) as exc:
            raise InvoiceParseError(f"OFD 读取失败：{exc}") from exc
        if not looks_like_vat_invoice(content):
            raise InvoiceParseError("OFD 中未找到发票内容")
        return parse_invoice_text(content, self.name)
