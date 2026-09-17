"""凭证识别入口：文字抽取 → 识别器 → 与文件名线索合并；永不抛异常。"""

import logging
from dataclasses import replace
from pathlib import Path

from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.evidence.base import (
    DOC_ITINERARY,
    DOC_ORDER,
    DOC_PAYMENT,
    DOC_UNKNOWN,
    FilenameHints,
    RecognizedEvidence,
)
from invoice_sorting.evidence.filename import file_key, filename_hints
from invoice_sorting.evidence.ocr import ocr_available
from invoice_sorting.evidence.parsing import CNY
from invoice_sorting.evidence.recognizers import best_match
from invoice_sorting.evidence.recognizers.ride import platform_name
from invoice_sorting.evidence.text import extract_text

logger = logging.getLogger(__name__)

__all__ = ["file_key", "filename_hints", "ocr_available", "recognize_evidence"]

RAW_TEXT_LIMIT = 20000
FILENAME_RECOGNIZER = "filename"
NO_RECOGNIZER = "none"
KIND_DOC_TYPES: dict[str, str] = {
    AttachmentKind.ORDER.value: DOC_ORDER,
    AttachmentKind.PAYMENT.value: DOC_PAYMENT,
    AttachmentKind.ITINERARY.value: DOC_ITINERARY,
}


def _merge_hints(
    result: RecognizedEvidence, hints: FilenameHints, original_name: str
) -> RecognizedEvidence:
    """识别器未给出的金额/日期用文件名补充；行程单平台名可取自文件名。"""
    updates: dict = {}
    if result.amount_cents is None and hints.amount_cents is not None and result.currency == CNY:
        updates.update(amount_cents=hints.amount_cents, cny_cents=hints.amount_cents)
    if result.occurred_on is None and hints.occurred_on is not None:
        updates["occurred_on"] = hints.occurred_on
    if not result.merchant and result.doc_type == DOC_ITINERARY:
        updates["merchant"] = platform_name(original_name)
    return replace(result, **updates)


def _from_filename(hints: FilenameHints) -> RecognizedEvidence:
    doc_type = KIND_DOC_TYPES.get(hints.kind or "", DOC_UNKNOWN)
    has_clue = (
        doc_type != DOC_UNKNOWN or hints.amount_cents is not None or hints.occurred_on is not None
    )
    return RecognizedEvidence(
        doc_type=doc_type,
        recognizer=FILENAME_RECOGNIZER if has_clue else NO_RECOGNIZER,
        amount_cents=hints.amount_cents,
        cny_cents=hints.amount_cents,
        occurred_on=hints.occurred_on,
    )


def _recognize(path: Path, original_name: str) -> RecognizedEvidence:
    hints = filename_hints(original_name)
    doc = extract_text(path)
    matched = best_match(doc)
    result = _merge_hints(matched, hints, original_name) if matched else _from_filename(hints)
    return replace(result, raw_text=doc.text[:RAW_TEXT_LIMIT])


def recognize_evidence(path: Path, original_name: str) -> RecognizedEvidence:
    """识别非发票凭证；任何异常记录 debug 日志并返回 unknown。"""
    try:
        return _recognize(path, original_name)
    except Exception as exc:  # 识别失败不能影响导入流程
        logger.debug("凭证识别失败 %s（%s）：%r", path, original_name, exc)
        return RecognizedEvidence(doc_type=DOC_UNKNOWN, recognizer=NO_RECOGNIZER)
