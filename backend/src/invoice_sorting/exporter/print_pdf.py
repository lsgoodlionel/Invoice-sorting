"""打印版 PDF：按序号与材料顺序合并 PDF 页与图片页（图片等比缩放到 A4，不变形）。"""

import io
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PyPdfError

from invoice_sorting.db.models import Attachment
from invoice_sorting.exporter.naming import PackageItem

logger = logging.getLogger(__name__)

PDF_MIME = "application/pdf"
IMAGE_MIMES = frozenset({"image/png", "image/jpeg", "image/webp"})
A4_WIDTH_PT = 595.28
A4_HEIGHT_PT = 841.89
POINTS_PER_INCH = 72
IMAGE_DPI = 150
PAGE_MARGIN_PX = 60  # 约 10mm
A4_WIDTH_PX = round(A4_WIDTH_PT / POINTS_PER_INCH * IMAGE_DPI)
A4_HEIGHT_PX = round(A4_HEIGHT_PT / POINTS_PER_INCH * IMAGE_DPI)

PathResolver = Callable[[Attachment], Path]


@dataclass(frozen=True)
class PrintResult:
    pdf_bytes: bytes
    skipped: dict[int, list[str]] = field(default_factory=dict)  # expense_id → 未合并的文件名

    def notes_for(self, expense_id: int) -> str:
        names = self.skipped.get(expense_id, [])
        return "；".join(f"{name} 未合并到打印版" for name in names)


def image_to_a4_pdf(source: Path) -> bytes:
    """把图片等比缩放后居中放到 A4 白底页面，返回单页 PDF。"""
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    if image.width > image.height:
        page_size = (A4_HEIGHT_PX, A4_WIDTH_PX)  # 横图用横向 A4
    else:
        page_size = (A4_WIDTH_PX, A4_HEIGHT_PX)
    box = (page_size[0] - 2 * PAGE_MARGIN_PX, page_size[1] - 2 * PAGE_MARGIN_PX)
    scale = min(box[0] / image.width, box[1] / image.height)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    resized = image.resize(size, Image.Resampling.LANCZOS)
    page = Image.new("RGB", page_size, "white")
    page.paste(resized, ((page_size[0] - size[0]) // 2, (page_size[1] - size[1]) // 2))
    buffer = io.BytesIO()
    page.save(buffer, format="PDF", resolution=IMAGE_DPI)
    return buffer.getvalue()


def _checked_pdf(source: Path | bytes) -> PdfReader:
    """完整解析一遍 PDF（写入内存副本），确保损坏文件在合并前就暴露出来。"""
    reader = PdfReader(io.BytesIO(source) if isinstance(source, bytes) else source)
    if reader.is_encrypted and not reader.decrypt(""):
        raise PyPdfError("PDF 已加密")
    copy = PdfWriter()
    for page in reader.pages:
        copy.add_page(page)
    buffer = io.BytesIO()
    copy.write(buffer)
    return PdfReader(io.BytesIO(buffer.getvalue()))


def _append_attachment(writer: PdfWriter, attachment: Attachment, path: Path) -> bool:
    """合并单个附件，成功返回 True；类型不支持、文件缺失或损坏时返回 False。"""
    if attachment.mime not in IMAGE_MIMES and attachment.mime != PDF_MIME:
        return False
    if not path.is_file():
        logger.warning("附件 #%s 文件缺失：%s", attachment.id, path)
        return False
    try:
        source = path if attachment.mime == PDF_MIME else image_to_a4_pdf(path)
        reader = _checked_pdf(source)
    except Exception as exc:  # noqa: BLE001 — 外部文件可能以任意方式损坏，记录后跳过
        logger.warning("附件 #%s 无法合并到打印版：%s", attachment.id, exc)
        return False
    for page in reader.pages:
        writer.add_page(page)
    return True


def build_print_pdf(items: list[PackageItem], resolve: PathResolver) -> PrintResult:
    writer = PdfWriter()
    skipped: dict[int, list[str]] = {}
    for item in items:
        for attachment in item.attachments:
            if _append_attachment(writer, attachment, resolve(attachment)):
                continue
            skipped.setdefault(item.expense.id, []).append(attachment.original_name)
    if len(writer.pages) == 0:
        writer.add_blank_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)
    buffer = io.BytesIO()
    writer.write(buffer)
    return PrintResult(pdf_bytes=buffer.getvalue(), skipped=skipped)
