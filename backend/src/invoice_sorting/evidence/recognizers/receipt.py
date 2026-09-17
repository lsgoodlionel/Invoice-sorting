"""Stripe 类收据/账单（中英文）：Receipt / Invoice number / Amount paid / Date paid / Total。"""

import re

from invoice_sorting.evidence.base import DOC_RECEIPT, RecognizedEvidence
from invoice_sorting.evidence.lines import EvidenceText, find_line, value_after
from invoice_sorting.evidence.parsing import (
    Money,
    find_all_dates,
    find_money,
    parse_date,
    strip_money,
)
from invoice_sorting.evidence.recognizers.common import (
    MIN_SCORE,
    Features,
    build,
    feature_score,
    find_card_last4,
    money_fields,
)

NAME = "receipt"
FEATURES = Features(
    groups=(
        ("收据", "receipt"),
        ("账单", "invoice"),
        ("收据编号", "receipt number"),
        ("账单编号", "invoice number"),
        ("付款日期", "date paid", "发出日期", "date of issue"),
        ("支付额", "amount paid", "应付金额", "amount due"),
        ("小计", "subtotal"),
        ("合计", "total"),
        ("描述", "description"),
        ("单价", "unit price"),
        ("收票人", "bill to"),
        ("支付记录", "payment history"),
    ),
    needed=6,
    anchors=("收据编号", "receipt number", "账单编号", "invoice number", "支付额", "amount paid"),
)
RECEIPT_NO_RE = re.compile(
    r"(?:收据编号|receipt\s*(?:number|no\.?|#))\s*:?\s*([A-Za-z0-9-]{4,})", re.I
)
INVOICE_NO_RE = re.compile(
    r"(?:账单编号|invoice\s*(?:number|no\.?|#))\s*:?\s*([A-Za-z0-9-]{4,})", re.I
)
HEADLINE_RE = re.compile(r"支付|应付|paid|due", re.I)
AMOUNT_LABELS = (r"支付额|amount paid", r"合计|(?<![a-z])total(?![a-z])", r"应付金额|amount due")
PAID_DATE_LABELS = (r"付款日期|date paid", r"发出日期|date of issue")
COMPANY_RE = re.compile(r"^(.*?\b(?:Inc|LLC|Ltd|Limited|GmbH|Corp|Corporation|PBC)\b\.?)")
TITLE_RE = re.compile(r"^(?:收据|账单|receipt|invoice)$", re.I)
LOGO_PREFIX_RE = re.compile(r"^[A-Za-z]\s+(?=\S{2,})")
ITEM_HEADER_RE = r"^(?:描述|description)(?:\s|$)"
TRAILING_NUMBERS_RE = re.compile(r"(?:\s+\d+)+\s*$")


def _reference(doc: EvidenceText, pattern: re.Pattern[str]) -> str:
    for line in doc.lines:
        match = pattern.search(line.text)
        if match and any(char.isdigit() for char in match.group(1)):
            return match.group(1).rstrip("-")
    return ""


def _headline(doc: EvidenceText) -> tuple[Money | None, list]:
    for line in doc.lines:
        money, dates = find_money(line.text), find_all_dates(line.text)
        if money and dates and HEADLINE_RE.search(line.text):
            return money, dates
    return None, []


def _labeled_amount(doc: EvidenceText) -> Money | None:
    for label in AMOUNT_LABELS:
        money = find_money(value_after(doc, label))
        if money:
            return money
    return None


def _merchant(doc: EvidenceText) -> str:
    for line in doc.lines:
        for box in line.boxes:
            match = COMPANY_RE.search(box.text)
            if match:
                return match.group(1).strip()
    for line in doc.lines:
        titles = [box for box in line.boxes if TITLE_RE.match(box.text)]
        if titles:
            others = " ".join(box.text for box in line.boxes if box not in titles)
            return LOGO_PREFIX_RE.sub("", others).strip()
    return ""


def _item_name(doc: EvidenceText) -> str:
    header = find_line(doc, ITEM_HEADER_RE)
    if header < 0 or header + 1 >= len(doc.lines):
        return ""
    first_box = doc.lines[header + 1].boxes[0].text
    return TRAILING_NUMBERS_RE.sub("", strip_money(first_box)).strip()


def _paid_date(doc: EvidenceText, headline_dates: list):
    labeled = [parse_date(value_after(doc, label)) for label in PAID_DATE_LABELS]
    candidates = [labeled[0], *headline_dates[:1], labeled[1], parse_date(doc.text)]
    return next((value for value in candidates if value is not None), None)


def recognize(doc: EvidenceText) -> RecognizedEvidence | None:
    score = feature_score(doc, FEATURES)
    if score < MIN_SCORE:
        return None
    headline_money, headline_dates = _headline(doc)
    money = headline_money or _labeled_amount(doc)
    return build(
        NAME,
        DOC_RECEIPT,
        score,
        occurred_on=_paid_date(doc, headline_dates),
        merchant=_merchant(doc),
        item_name=_item_name(doc),
        order_no=_reference(doc, RECEIPT_NO_RE) or _reference(doc, INVOICE_NO_RE),
        card_last4=find_card_last4(doc.text),
        **money_fields(money),
    )
