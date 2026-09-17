"""非发票凭证识别结果 → 附件类型与 EvidenceData（导入、补传、重新识别共用）。

识别函数经由本模块引用，测试可 monkeypatch `recognize_evidence` / `filename_hints`。
"""

import logging
from pathlib import Path

from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.db.models import Attachment, EvidenceData
from invoice_sorting.evidence import (
    FilenameHints,
    RecognizedEvidence,
    filename_hints,
    recognize_evidence,
)
from invoice_sorting.evidence.base import (
    DOC_ITINERARY,
    DOC_ORDER,
    DOC_PAYMENT,
    DOC_RECEIPT,
    DOC_UNKNOWN,
)

logger = logging.getLogger(__name__)

RAW_TEXT_LIMIT = 20000
FAILED_RECOGNIZER = "error"
DOC_TYPE_KINDS: dict[str, AttachmentKind] = {
    DOC_ORDER: AttachmentKind.ORDER,
    DOC_RECEIPT: AttachmentKind.ORDER,
    DOC_PAYMENT: AttachmentKind.PAYMENT,
    DOC_ITINERARY: AttachmentKind.ITINERARY,
}
# 重新识别时覆盖的字段（confirmed 保留）
EVIDENCE_FIELDS = (
    "doc_type",
    "recognizer",
    "amount_cents",
    "currency",
    "cny_cents",
    "occurred_on",
    "merchant",
    "item_name",
    "order_no",
    "card_last4",
    "is_foreign",
)


def recognize_file(path: Path, original_name: str) -> RecognizedEvidence:
    """识别器约定不抛异常；这里再兜底一次，失败时返回未识别结果。"""
    try:
        return recognize_evidence(path, original_name)
    except Exception:
        logger.exception("凭证识别失败：%s", original_name)
        return RecognizedEvidence(doc_type=DOC_UNKNOWN, recognizer=FAILED_RECOGNIZER)


def safe_filename_hints(original_name: str) -> FilenameHints | None:
    try:
        return filename_hints(original_name or "")
    except Exception:
        logger.exception("文件名线索识别失败：%s", original_name)
        return None


def _hinted_kind(original_name: str) -> AttachmentKind | None:
    hints = safe_filename_hints(original_name)
    if hints is None or not hints.kind:
        return None
    try:
        return AttachmentKind(hints.kind)
    except ValueError:
        return None


def kind_for_evidence(
    recognized: RecognizedEvidence, original_name: str, fallback: AttachmentKind
) -> AttachmentKind:
    """识别出的凭证类型优先，其次文件名线索，最后用调用方给的猜测类型。"""
    known = DOC_TYPE_KINDS.get(recognized.doc_type)
    if known is not None:
        return known
    return _hinted_kind(original_name) or fallback


def apply_evidence(attachment: Attachment, recognized: RecognizedEvidence) -> EvidenceData:
    """写入或更新附件的 EvidenceData；已有记录保留 confirmed。"""
    evidence = attachment.evidence_data
    if evidence is None:
        evidence = EvidenceData(confirmed=False)
        attachment.evidence_data = evidence
    for name in EVIDENCE_FIELDS:
        setattr(evidence, name, getattr(recognized, name))
    evidence.currency = (recognized.currency or "CNY").upper()
    evidence.merchant = recognized.merchant or ""
    evidence.item_name = recognized.item_name or ""
    evidence.order_no = recognized.order_no or ""
    evidence.card_last4 = recognized.card_last4 or ""
    evidence.file_key = attachment.file_key or ""
    evidence.raw_text = (recognized.raw_text or "")[:RAW_TEXT_LIMIT]
    return evidence
