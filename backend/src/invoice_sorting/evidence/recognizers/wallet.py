"""微信/支付宝账单详情：交易单号、商户单号、支付时间、收款方、当前状态。"""

import re

from invoice_sorting.evidence.base import DOC_PAYMENT, RecognizedEvidence
from invoice_sorting.evidence.lines import EvidenceText, value_after
from invoice_sorting.evidence.parsing import CNY, Money, find_plain_amount, parse_date
from invoice_sorting.evidence.recognizers.common import (
    MIN_SCORE,
    Features,
    build,
    feature_score,
    first_digits,
    first_reference,
    money_fields,
)

NAME = "wallet_bill"
FEATURES = Features(
    groups=(
        ("交易单号",),
        ("商户单号", "商家订单号"),
        ("支付时间", "创建时间"),
        ("收款方", "商户全称"),
        ("当前状态", "交易状态"),
        ("支付成功", "交易成功", "已支付", "对方已收钱"),
        ("账单详情",),
        ("支付方式", "付款方式"),
        ("商品",),
        ("收单机构", "账单分类"),
    ),
    needed=5,
    anchors=("交易单号", "商户单号", "商家订单号", "收款方", "商户全称"),
)
AMOUNT_LINE_RE = re.compile(r"^[-+]?\s*¥?\s*\d[\d,]*\.\d{2}$")
TIME_LABEL = r"支付时间|付款时间|交易时间|创建时间"
MERCHANT_LABEL = r"收款方全称|商户全称|收款方"
ITEM_LABEL = r"商品说明|商品"
TRADE_NO_LABEL = r"交易单号|(?<!商家)(?<!商户)订单号"
MERCHANT_NO_LABEL = r"商户单号|商家订单号"
PAREN_CARD_RE = re.compile(r"\((\d{4})\)")
STATUS_WORDS = ("账单详情", "当前状态", "交易成功", "支付成功")


def _amount(doc: EvidenceText) -> Money | None:
    for line in doc.lines:
        if AMOUNT_LINE_RE.match(line.text):
            cents = find_plain_amount(line.text)
            return Money(cents, CNY) if cents is not None else None
    cents = find_plain_amount(value_after(doc, r"付款金额|支付金额"))
    return Money(cents, CNY) if cents is not None else None


def _merchant(doc: EvidenceText) -> str:
    labeled = value_after(doc, MERCHANT_LABEL)
    if labeled:
        return labeled
    for line in doc.lines:
        text = line.text
        if not AMOUNT_LINE_RE.match(text) and not any(word in text for word in STATUS_WORDS):
            return text
    return ""


def recognize(doc: EvidenceText) -> RecognizedEvidence | None:
    score = feature_score(doc, FEATURES)
    if score < MIN_SCORE:
        return None
    card = PAREN_CARD_RE.search(value_after(doc, r"支付方式|付款方式"))
    order_no = first_digits(value_after(doc, TRADE_NO_LABEL)) or first_reference(
        value_after(doc, MERCHANT_NO_LABEL)
    )
    return build(
        NAME,
        DOC_PAYMENT,
        score,
        occurred_on=parse_date(value_after(doc, TIME_LABEL)) or parse_date(doc.text),
        merchant=_merchant(doc),
        item_name=value_after(doc, ITEM_LABEL),
        order_no=order_no,
        card_last4=card.group(1) if card else "",
        **money_fields(_amount(doc)),
    )
