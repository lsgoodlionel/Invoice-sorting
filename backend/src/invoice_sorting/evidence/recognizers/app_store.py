"""App Store 订阅订单（“订单详细信息 / 订单日期 / 订单号 / 文稿编号 / Apple 账户”）。"""

import re

from invoice_sorting.evidence.base import DOC_ORDER, RecognizedEvidence
from invoice_sorting.evidence.lines import EvidenceText, value_after, value_below
from invoice_sorting.evidence.parsing import Money, find_money, parse_date, strip_money
from invoice_sorting.evidence.recognizers.common import (
    MIN_SCORE,
    Features,
    build,
    feature_score,
    money_fields,
)

NAME = "app_store_order"
MERCHANT = "Apple"
FEATURES = Features(
    groups=(
        ("订单详细信息", "订单详情", "order details"),
        ("订单日期", "order date"),
        ("订单号", "order id"),
        ("文稿编号", "document no"),
        ("Apple 账户", "Apple Account", "Apple ID"),
        ("账单寄送地址", "billing address", "billed to"),
        ("订阅续期", "首个订阅", "重新发送收据", "管理订阅", "resend receipt", "renewal"),
    ),
    needed=4,
    anchors=("文稿编号", "document no", "Apple 账户", "Apple Account", "Apple ID"),
)
ORDER_DATE_LABEL = r"订单日期|order date|date"
ORDER_NO_LABEL = r"订单号|order id"
DOCUMENT_NO_LABEL = r"文稿编号|document(?:\s+no\.?)?"
RECEIPT_LABEL = r"receipt"
APPLE_ORDER_NO_RE = re.compile(r"(?<![A-Z0-9])(M[A-Z0-9]{9})(?![A-Z0-9])")
DOCUMENT_NO_RE = re.compile(r"(?<!\d)(\d{8,})(?!\d)")
DOCUMENT_VALUE_RE = re.compile(
    rf"(?:{DOCUMENT_NO_LABEL})\s*:?[ \t\n]*(\d{{8,}})", re.IGNORECASE
)
TRAILING_CURRENCY_RE = re.compile(r"\s+(?:USD|JPY|CNY|RMB|EUR|GBP|HKD)\s*$", re.IGNORECASE)


def _first_money_line(doc: EvidenceText) -> tuple[str, Money | None]:
    for line in doc.lines:
        money = find_money(line.text)
        if money is not None:
            return line.text, money
    return "", None


def _order_no(doc: EvidenceText) -> str:
    candidates = (
        value_below(doc, rf"^(?:{ORDER_NO_LABEL})$"),
        value_after(doc, ORDER_NO_LABEL),
        doc.text,
    )
    for text in candidates:
        match = APPLE_ORDER_NO_RE.search(text)
        if match:
            return match.group(1)
    return ""


def _document_no(doc: EvidenceText) -> str:
    direct = DOCUMENT_VALUE_RE.search(doc.text)
    if direct:
        return direct.group(1)
    candidates = (
        value_below(doc, rf"^(?:{DOCUMENT_NO_LABEL})$"),
        value_after(doc, DOCUMENT_NO_LABEL),
    )
    for text in candidates:
        matched = DOCUMENT_NO_RE.search(text)
        if matched:
            return matched.group(1)
    return ""


def _item_name(doc: EvidenceText, money_line: str) -> str:
    inline = TRAILING_CURRENCY_RE.sub("", strip_money(money_line)).strip()
    if inline:
        return inline
    values: list[str] = []
    inside = False
    for line in doc.lines:
        text = line.text.strip()
        if text.lower() == "app store":
            inside = True
            continue
        if not inside:
            continue
        if "in-app purchase" in text.lower():
            break
        if find_money(text) is not None:
            break
        values.append(text)
    if values:
        return " ".join(values)
    lines = [line.text.strip() for line in doc.lines]
    try:
        money_index = lines.index(money_line)
    except ValueError:
        return ""
    backwards: list[str] = []
    for text in reversed(lines[:money_index]):
        lowered = text.lower()
        if lowered.startswith(("renews ", "renewal ")):
            continue
        if lowered.startswith("save ") or lowered.startswith("apple account"):
            break
        if find_money(text) is not None:
            break
        backwards.append(text)
        if len(backwards) == 2:
            break
    return " ".join(reversed(backwards))


def recognize(doc: EvidenceText) -> RecognizedEvidence | None:
    score = feature_score(doc, FEATURES)
    if score < MIN_SCORE:
        return None
    item_line, money = _first_money_line(doc)
    occurred_on = (
        parse_date(value_below(doc, rf"^(?:{RECEIPT_LABEL})$"))
        or parse_date(value_after(doc, RECEIPT_LABEL))
        or parse_date(value_below(doc, rf"^(?:{ORDER_DATE_LABEL})$"))
        or parse_date(value_after(doc, ORDER_DATE_LABEL))
        or parse_date(doc.text)
    )
    document_no = _document_no(doc)
    return build(
        NAME,
        DOC_ORDER,
        score,
        occurred_on=occurred_on,
        merchant=MERCHANT,
        item_name=_item_name(doc, item_line),
        order_no=_order_no(doc),
        details={"document_no": document_no} if document_no else {},
        **money_fields(money),
    )
