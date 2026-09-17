"""识别器共用：特征词打分、结果构造、卡号末四位与编号提取。"""

import re
from dataclasses import dataclass

from invoice_sorting.evidence.base import RecognizedEvidence
from invoice_sorting.evidence.lines import EvidenceText
from invoice_sorting.evidence.parsing import CNY, Money

MIN_SCORE = 0.2  # 低于该分数的识别器直接放弃，不再提取字段
NO_ANCHOR_CAP = 0.3  # 缺少锚点特征词时的置信度上限
NO_AMOUNT_FACTOR = 0.6  # 未提取到金额时的置信度折扣

CARD_RE = re.compile(
    r"(?:visa|master\s*card|amex|american\s+express|unionpay|银联|jcb|discover)"
    r"\s*[-–—•*·.]*\s*(?:ending\s+in\s*)?(\d{4})(?!\d)"
    r"|[•*]{2,}\s*(\d{4})(?!\d)",
    re.IGNORECASE,
)
REFERENCE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{3,}")
DIGITS_RE = re.compile(r"\d{6,32}")


@dataclass(frozen=True)
class Features:
    groups: tuple[tuple[str, ...], ...]  # 每组任一词出现即命中该组
    needed: int  # 命中组数达到该值即满分
    anchors: tuple[str, ...]  # 至少出现一个，否则置信度封顶


def _squash(word: str) -> str:
    return re.sub(r"\s+", "", word).lower()


def feature_score(doc: EvidenceText, features: Features) -> float:
    flat = doc.compact
    hits = sum(any(_squash(word) in flat for word in group) for group in features.groups)
    score = min(1.0, hits / features.needed)
    has_anchor = any(_squash(word) in flat for word in features.anchors)
    return score if has_anchor else min(score, NO_ANCHOR_CAP)


def confidence(score: float, amount: int | None) -> float:
    return round(score if amount is not None else score * NO_AMOUNT_FACTOR, 3)


def money_fields(money: Money | None) -> dict:
    """金额相关字段：amount_cents、currency、cny_cents、is_foreign（按币种）。"""
    if money is None:
        return {"amount_cents": None, "currency": CNY, "cny_cents": None, "is_foreign": False}
    is_cny = money.currency == CNY
    return {
        "amount_cents": money.cents,
        "currency": money.currency,
        "cny_cents": money.cents if is_cny else None,
        "is_foreign": not is_cny,
    }


def build(name: str, doc_type: str, score: float, **fields) -> RecognizedEvidence:
    amount = fields.get("amount_cents")
    return RecognizedEvidence(
        doc_type=doc_type, recognizer=name, confidence=confidence(score, amount), **fields
    )


def find_card_last4(text: str) -> str:
    match = CARD_RE.search(text)
    return (match.group(1) or match.group(2)) if match else ""


def first_reference(text: str) -> str:
    """值文本中的第一个编号（含数字的字母数字串，允许连字符）。"""
    for match in REFERENCE_RE.finditer(text):
        if any(char.isdigit() for char in match.group(0)):
            return match.group(0)
    return ""


def first_digits(text: str) -> str:
    match = DIGITS_RE.search(text)
    return match.group(0) if match else ""
