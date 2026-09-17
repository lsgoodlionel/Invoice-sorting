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
ORDER_DATE_LABEL = r"订单日期|order date"
ORDER_NO_LABEL = r"订单号|order id"
APPLE_ORDER_NO_RE = re.compile(r"(?<![A-Z0-9])(M[A-Z0-9]{9})(?![A-Z0-9])")


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


def recognize(doc: EvidenceText) -> RecognizedEvidence | None:
    score = feature_score(doc, FEATURES)
    if score < MIN_SCORE:
        return None
    item_line, money = _first_money_line(doc)
    occurred_on = (
        parse_date(value_below(doc, rf"^(?:{ORDER_DATE_LABEL})$"))
        or parse_date(value_after(doc, ORDER_DATE_LABEL))
        or parse_date(doc.text)
    )
    return build(
        NAME,
        DOC_ORDER,
        score,
        occurred_on=occurred_on,
        merchant=MERCHANT,
        item_name=strip_money(item_line),
        order_no=_order_no(doc),
        **money_fields(money),
    )
