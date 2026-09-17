"""凭证文字来源：图片 OCR；PDF 文本层，无文本层时渲染首页 OCR。"""

import logging
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageOps

from invoice_sorting.evidence.lines import EvidenceText, lines_from_boxes, lines_from_text
from invoice_sorting.evidence.ocr import ocr_available, ocr_image
from invoice_sorting.parsers.pdf_text import extract_pdf_text

logger = logging.getLogger(__name__)

IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif"})
PDF_SUFFIX = ".pdf"
PDF_MAX_PAGES = 5
MAX_OCR_SIDE = 2400  # 最长边超过该像素先缩小，限制 OCR 内存
PDF_RENDER_SCALE = 2.0  # 72dpi × 2


def limit_size(image: Image.Image, max_side: int = MAX_OCR_SIDE) -> Image.Image:
    """最长边超过 max_side 时等比缩小，返回新图；否则原样返回。"""
    width, height = image.size
    longest = max(width, height)
    if longest <= max_side:
        return image
    ratio = max_side / longest
    size = (max(1, round(width * ratio)), max(1, round(height * ratio)))
    return image.resize(size, Image.Resampling.LANCZOS)


def load_image(path: Path) -> Image.Image | None:
    """打开图片（按 EXIF 旋转、转 RGB、限制尺寸）；无法识别的格式（如无插件的 HEIC）返回 None。"""
    try:
        with Image.open(path) as opened:
            upright = ImageOps.exif_transpose(opened) or opened
            upright.load()
            return limit_size(upright.convert("RGB"))
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        logger.debug("无法打开图片 %s：%r", path, exc)
        return None


def render_pdf_first_page(path: Path) -> Image.Image | None:
    """渲染 PDF 首页为图片（与缩略图共用 PDFium 锁串行化）；失败返回 None。"""
    from invoice_sorting.attachments.thumbnails import PDFIUM_LOCK

    try:
        with PDFIUM_LOCK:
            document = pdfium.PdfDocument(path)
            try:
                page = document[0]
                width, height = page.get_size()
                scale = min(PDF_RENDER_SCALE, MAX_OCR_SIDE / max(width, height, 1))
                return page.render(scale=scale).to_pil().convert("RGB")
            finally:
                document.close()
    except Exception as exc:  # PDFium 对损坏文件抛出多种异常
        logger.debug("PDF 首页渲染失败 %s：%r", path, exc)
        return None


def _ocr_text(image: Image.Image | None) -> EvidenceText:
    if image is None:
        return EvidenceText()
    return EvidenceText(lines_from_boxes(ocr_image(image)))


def _pdf_text(path: Path) -> EvidenceText:
    text = extract_pdf_text(path, max_pages=PDF_MAX_PAGES)
    if text:
        return lines_from_text(text)
    if not ocr_available():
        return EvidenceText()
    return _ocr_text(render_pdf_first_page(path))


def extract_text(path: Path) -> EvidenceText:
    """按扩展名选择文字来源；不支持的类型或 OCR 不可用时返回空文档。"""
    suffix = path.suffix.lower()
    if suffix == PDF_SUFFIX:
        return _pdf_text(path)
    if suffix in IMAGE_SUFFIXES and ocr_available():
        return _ocr_text(load_image(path))
    return EvidenceText()
