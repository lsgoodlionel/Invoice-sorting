"""识别器注册表：所有识别器打分，取置信度最高且达到阈值者。"""

import logging
from collections.abc import Callable

from invoice_sorting.evidence.base import RecognizedEvidence
from invoice_sorting.evidence.lines import EvidenceText
from invoice_sorting.evidence.recognizers import (
    app_store,
    bank,
    ecommerce,
    hotel_booking,
    receipt,
    ride,
    transport_booking,
    wallet,
)

logger = logging.getLogger(__name__)

MIN_CONFIDENCE = 0.4

Recognizer = Callable[[EvidenceText], RecognizedEvidence | None]

# 同分时取靠前者：专用的差旅识别器排在通用订单/账单识别器之前
RECOGNIZERS: tuple[Recognizer, ...] = (
    hotel_booking.recognize,
    transport_booking.recognize,
    app_store.recognize,
    receipt.recognize,
    bank.recognize,
    ecommerce.recognize,
    wallet.recognize,
    ride.recognize,
)


def _safe_run(recognizer: Recognizer, doc: EvidenceText) -> RecognizedEvidence | None:
    try:
        return recognizer(doc)
    except Exception as exc:  # 单个识别器异常不影响其他识别器
        logger.debug("凭证识别器 %r 异常：%r", recognizer, exc)
        return None


def best_match(doc: EvidenceText) -> RecognizedEvidence | None:
    """置信度最高且 ≥ MIN_CONFIDENCE 的识别结果；无则 None。"""
    if not doc.lines:
        return None
    results = [result for result in (_safe_run(item, doc) for item in RECOGNIZERS) if result]
    best = max(results, key=lambda result: result.confidence, default=None)
    return best if best is not None and best.confidence >= MIN_CONFIDENCE else None
