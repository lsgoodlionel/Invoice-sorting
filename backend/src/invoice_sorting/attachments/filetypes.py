"""按文件内容魔数识别真实类型，并按文件名关键词猜测附件类型。"""

from pathlib import Path

from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.common.errors import AppError
from invoice_sorting.config import MAX_UPLOAD_BYTES

SNIFF_BYTES = 1024
HEIC_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}
XML_BOMS = (b"\xef\xbb\xbf",)

# 顺序即优先级：“报账单”须先于“账单”判断
KIND_KEYWORDS: tuple[tuple[AttachmentKind, tuple[str, ...]], ...] = (
    (AttachmentKind.SOFTWARE_FORM, ("报账单",)),
    (AttachmentKind.INVOICE, ("发票", "invoice", "dzfp")),
    (AttachmentKind.MEAL_FORM, ("工作餐",)),
    (AttachmentKind.ACCEPTANCE, ("验收",)),
    (AttachmentKind.CONTRACT, ("合同", "协议")),
    (AttachmentKind.APPLICATION, ("申购",)),
    (AttachmentKind.ITINERARY, ("行程",)),
    (AttachmentKind.MEETING, ("会议", "签到", "议程")),
    (AttachmentKind.ORDER, ("订单", "order", "明细", "清单")),
    (AttachmentKind.PAYMENT, ("支付", "付款", "账单", "交易", "pay")),
    (AttachmentKind.STATEMENT, ("说明",)),
)

MIME_EXTENSIONS: dict[str, str] = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "application/ofd": ".ofd",
    "application/zip": ".zip",
    "application/xml": ".xml",
}


def guess_kind(original_name: str) -> AttachmentKind:
    stem = Path(original_name).stem.lower()
    for kind, keywords in KIND_KEYWORDS:
        if any(keyword in stem for keyword in keywords):
            return kind
    return AttachmentKind.OTHER


def _is_xml(head: bytes) -> bool:
    for bom in XML_BOMS:
        head = head.removeprefix(bom)
    text = head.lstrip()
    if not text.startswith(b"<"):
        return False
    try:
        text.decode("utf-8")
    except UnicodeDecodeError as exc:
        # 截断处可能落在多字节字符中间，只要前面部分合法即可
        if exc.start < len(text) - 3:
            return False
    return text.startswith(b"<?xml") or text[1:2].isalpha()


def _sniff_mime(head: bytes, original_name: str) -> str | None:
    if b"%PDF-" in head[:SNIFF_BYTES]:
        return "application/pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:8] == b"ftyp" and head[8:12] in HEIC_BRANDS:
        return "image/heic"
    if head.startswith(b"PK\x03\x04"):
        is_ofd = original_name.lower().endswith(".ofd")
        return "application/ofd" if is_ofd else "application/zip"
    if _is_xml(head):
        return "application/xml"
    return None


def validate_file(src: Path, original_name: str) -> tuple[str, int]:
    """校验大小与真实类型，返回 (mime, size)。不合规时抛 AppError。"""
    size = src.stat().st_size
    if size == 0:
        raise AppError(f"文件为空：{original_name}")
    if size > MAX_UPLOAD_BYTES:
        limit_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        raise AppError(f"文件超过 {limit_mb}MB 上限：{original_name}")
    with src.open("rb") as handle:
        head = handle.read(SNIFF_BYTES)
    mime = _sniff_mime(head, original_name)
    if mime is None:
        raise AppError(f"不支持的文件类型：{original_name}（仅支持 PDF、OFD、XML、图片、ZIP）")
    return mime, size


def extension_for(original_name: str, mime: str) -> str:
    suffix = Path(original_name).suffix.lower()
    if suffix and len(suffix) <= 6 and suffix[1:].isalnum():
        return suffix
    return MIME_EXTENSIONS.get(mime, "")
