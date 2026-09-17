"""银行卡交易明细（“明细详情 / 交易卡号(末四位) / 交易时间 / 原始交易金额 / 入账详情”）。"""

import re

from invoice_sorting.evidence.base import DOC_PAYMENT, RecognizedEvidence
from invoice_sorting.evidence.lines import EvidenceText, find_line, value_after
from invoice_sorting.evidence.parsing import CNY, Money, find_money, parse_date
from invoice_sorting.evidence.recognizers.common import (
    MIN_SCORE,
    Features,
    build,
    feature_score,
    money_fields,
)

NAME = "bank_transaction"
FEATURES = Features(
    groups=(
        ("明细详情", "交易详情"),
        ("交易卡号", "卡号末四位"),
        ("交易时间",),
        ("原始交易金额",),
        ("原始交易币种",),
        ("境内外交易标识",),
        ("交易国家或地区",),
        ("商户类别",),
        ("入账详情", "入账金额"),
        ("交易地点",),
    ),
    needed=5,
    anchors=("交易卡号", "原始交易", "境内外交易标识", "入账详情"),
)
POSTED_RE = re.compile(r"(?:消费|入账|支出)\s*\d[\d,]*(?:\.\d{1,2})?\s*元")
CARD_LABEL = r"交易卡号(?:\(末四位\))?|卡号末四位"
MERCHANT_AMOUNT_RE = re.compile(r"[-+]{1,2}\s*\d[\d,]*\.\d{2}")
COUNTRY_CODES = frozenset(
    {"USA", "GBR", "IRL", "SGP", "HKG", "JPN", "DEU", "FRA", "NLD", "CAN", "AUS", "KOR", "CHN"}
)
DOMESTIC_COUNTRIES = ("中国", "CHN")


def _posted_amount(doc: EvidenceText) -> Money | None:
    for line in doc.lines:
        match = POSTED_RE.search(line.text)
        if match:
            return find_money(match.group(0))
    return None


def _headline(doc: EvidenceText) -> tuple[int, Money | None]:
    for index, line in enumerate(doc.lines):
        money = find_money(line.text)
        if money is not None and money.currency == CNY:
            return index, money
    return -1, None


def clean_merchant(text: str) -> str:
    """“PP*APPLE.COM/BILL 4029357733 USA-+144.26” → “PP*APPLE.COM/BILL”。"""
    tokens = MERCHANT_AMOUNT_RE.split(text, maxsplit=1)[0].split()
    end = len(tokens)
    while end and (tokens[end - 1].isdigit() or tokens[end - 1].strip("-+") in COUNTRY_CODES):
        end -= 1
    return " ".join(tokens[:end]).strip(" -+")


def _merchant(doc: EvidenceText, headline: int) -> str:
    card_line = find_line(doc, CARD_LABEL)
    below = headline + 1
    if headline < 0 or below >= len(doc.lines) or (0 <= card_line <= below):
        return ""
    return clean_merchant(doc.lines[below].text)


def _is_foreign(doc: EvidenceText, original_currency: str) -> bool:
    flag = value_after(doc, "境内外交易标识")
    if flag:
        return "境外" in flag
    country = value_after(doc, "交易国家或地区")
    if country:
        return not any(name in country for name in DOMESTIC_COUNTRIES)
    return original_currency not in ("", CNY)


def _original_currency(doc: EvidenceText) -> str:
    match = re.search(r"[A-Z]{3}", value_after(doc, "原始交易币种"))
    return match.group(0) if match else ""


def _original_note(doc: EvidenceText, original_currency: str) -> str:
    """原币非人民币时保留原始金额信息，如“原币 USD 15.00”。"""
    if original_currency in ("", CNY):
        return ""
    return f"原币 {original_currency} {value_after(doc, '原始交易金额')}".strip()


def recognize(doc: EvidenceText) -> RecognizedEvidence | None:
    score = feature_score(doc, FEATURES)
    if score < MIN_SCORE:
        return None
    headline, headline_money = _headline(doc)
    card = re.search(r"\d{4}", value_after(doc, CARD_LABEL))
    original_currency = _original_currency(doc)
    fields = {
        **money_fields(_posted_amount(doc) or headline_money),
        "is_foreign": _is_foreign(doc, original_currency),
    }
    return build(
        NAME,
        DOC_PAYMENT,
        score,
        occurred_on=parse_date(value_after(doc, "交易时间|交易日期")) or parse_date(doc.text),
        merchant=_merchant(doc, headline),
        item_name=_original_note(doc, original_currency),
        card_last4=card.group(0) if card else "",
        **fields,
    )
