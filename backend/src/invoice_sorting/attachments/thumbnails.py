"""缩略图：PDF 首页 / 图片缩放，最长边 480px，缓存到 data_dir/.thumbs/。"""

import logging
import threading
import uuid
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, UnidentifiedImageError

from invoice_sorting.attachments.storage import absolute_path
from invoice_sorting.common.errors import AppError, NotFoundError
from invoice_sorting.config import Settings
from invoice_sorting.db.models import Attachment

logger = logging.getLogger(__name__)

THUMB_MAX_PX = 480
THUMB_DIRNAME = ".thumbs"
PDF_OVERSAMPLE = 2
RASTER_MIMES = frozenset({"image/png", "image/jpeg", "image/webp"})

# PDFium 不是线程安全的，进程内所有渲染必须串行，否则会段错误崩溃
PDFIUM_LOCK = threading.Lock()


def thumbnail_cache_path(settings: Settings, attachment: Attachment) -> Path:
    return settings.data_dir / THUMB_DIRNAME / f"{attachment.sha256}.png"


def _render_pdf(source: Path) -> Image.Image:
    with PDFIUM_LOCK:
        document = pdfium.PdfDocument(source)
        try:
            page = document[0]
            width, height = page.get_size()
            scale = THUMB_MAX_PX * PDF_OVERSAMPLE / max(width, height, 1)
            return page.render(scale=scale).to_pil()
        finally:
            document.close()


def _open_image(source: Path) -> Image.Image:
    with Image.open(source) as image:
        image.load()
        return image.copy()


def _build(source: Path, mime: str) -> Image.Image:
    if mime == "application/pdf":
        image = _render_pdf(source)
    elif mime in RASTER_MIMES:
        image = _open_image(source)
    else:
        raise NotFoundError("缩略图")
    image = image.convert("RGBA" if image.mode in ("RGBA", "LA", "P") else "RGB")
    image.thumbnail((THUMB_MAX_PX, THUMB_MAX_PX))
    return image


def get_thumbnail(settings: Settings, attachment: Attachment) -> Path:
    """返回缩略图文件路径；不支持的类型抛 NotFoundError。"""
    cache = thumbnail_cache_path(settings, attachment)
    if cache.is_file():
        return cache
    source = absolute_path(settings, attachment)
    if not source.is_file():
        raise NotFoundError("附件文件")
    try:
        image = _build(source, attachment.mime)
    except (pdfium.PdfiumError, UnidentifiedImageError, OSError) as exc:
        logger.warning("生成缩略图失败 attachment=%s: %s", attachment.id, exc)
        raise AppError("无法生成缩略图", status_code=404) from exc
    cache.parent.mkdir(parents=True, exist_ok=True)
    partial = cache.with_name(f"{cache.stem}.{uuid.uuid4().hex}.tmp")
    image.save(partial, format="PNG")
    partial.replace(cache)
    return cache


def remove_thumbnail(settings: Settings, attachment: Attachment) -> None:
    thumbnail_cache_path(settings, attachment).unlink(missing_ok=True)
