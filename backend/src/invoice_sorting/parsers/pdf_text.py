"""带保护的 PDF 文本提取：页数上限、时间预算、文件大小上限，异常统一返回 None。"""

import logging
import time
from pathlib import Path

import pdfplumber

from invoice_sorting.parsers.layout import PageWords, Word

logger = logging.getLogger(__name__)

MAX_PAGES = 10
MAX_FILE_BYTES = 30 * 1024 * 1024
TIME_BUDGET_SECONDS = 10.0
PDF_MAGIC = b"%PDF"


def _is_readable_pdf(path: Path) -> bool:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            logger.debug("PDF 超过大小上限，跳过：%s", path)
            return False
        with path.open("rb") as handle:
            return PDF_MAGIC in handle.read(1024)
    except OSError as exc:
        logger.debug("无法读取 PDF %s：%s", path, exc)
        return False


def extract_pdf_text(path: Path, max_pages: int = MAX_PAGES) -> str | None:
    """提取前 max_pages 页文本；超出时间预算即停止；加密/损坏/无文本返回 None。"""
    if not _is_readable_pdf(path):
        return None
    started = time.monotonic()
    texts: list[str] = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages[:max_pages]:
                texts.append(page.extract_text() or "")
                if time.monotonic() - started > TIME_BUDGET_SECONDS:
                    logger.debug("PDF 文本提取超出时间预算：%s", path)
                    break
    except Exception as exc:  # pdfminer 可能抛出任意异常
        logger.debug("PDF 文本提取失败 %s：%r", path, exc)
        return None
    text = "\n".join(texts).strip()
    return text or None


WORD_X_TOLERANCE = 1.5
WORD_Y_TOLERANCE = 2.0


def _to_word(raw: dict) -> Word:
    return Word(
        float(raw["x0"]), float(raw["x1"]), float(raw["top"]), float(raw["bottom"]), raw["text"]
    )


def extract_page_words(path: Path) -> PageWords | None:
    """提取首页所有词及坐标，供购销方分栏与项目名称列定位；失败返回 None。"""
    if not _is_readable_pdf(path):
        return None
    try:
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                return None
            page = pdf.pages[0]
            raw_words = page.extract_words(
                x_tolerance=WORD_X_TOLERANCE, y_tolerance=WORD_Y_TOLERANCE
            )
            width = float(page.width)
    except Exception as exc:  # pdfminer 可能抛出任意异常
        logger.debug("PDF 坐标提取失败 %s：%r", path, exc)
        return None
    return PageWords(width=width, words=tuple(_to_word(raw) for raw in raw_words))


def pdf_text_for_detection(path: Path, text: str | None) -> str | None:
    """供 can_parse 使用：已给文本（注册表已嗅探过文件头）直接用，否则仅对 .pdf 提取。"""
    if text is not None:
        return text
    return extract_pdf_text(path) if path.suffix.lower() == ".pdf" else None
