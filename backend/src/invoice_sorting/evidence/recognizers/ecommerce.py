"""电商订单截图（京东/淘宝/天猫/拼多多）：实付款、订单编号、支付时间、店铺名、商品名。"""

import re

from invoice_sorting.evidence.base import DOC_ORDER, RecognizedEvidence
from invoice_sorting.evidence.lines import EvidenceText, TextLine, find_line, value_after
from invoice_sorting.evidence.parsing import Money, find_all_money, find_money, parse_date
from invoice_sorting.evidence.recognizers.common import (
    MIN_SCORE,
    Features,
    build,
    feature_score,
    first_digits,
    money_fields,
)

NAME = "jd_order"
FEATURES = Features(
    groups=(
        ("实付款", "实付"),
        ("订单编号",),
        ("支付方式", "付款方式"),
        ("支付时间", "付款时间", "成交时间"),
        ("下单时间", "创建时间"),
        ("交易快照",),
        ("旗舰店", "专营店", "专卖店", "店铺", "自营"),
        ("数量×", "数量x"),
        ("合计",),
        ("到手", "商品总价", "运费", "退款/售后", "加购物车"),
    ),
    needed=5,
    anchors=("实付", "订单编号"),
)
PAID_LABEL = r"实付款|实付"
PAY_TIME_LABELS = (r"支付时间|付款时间|成交时间", r"下单时间|创建时间")
STORE_RE = re.compile(r"旗舰店|专营店|专卖店|店铺|店>?$")
STORE_SCAN_LINES = 5
STORE_NOISE_RE = re.compile(r"^自营\s*|\s*>\s*$")
ITEM_NOISE = frozenset({"京东超市", "天猫超市", "自营", "LOGO"})
ELLIPSIS_RE = re.compile(r"(?:\.{2,}|…+)$")
PLATFORM_PREFIX_RE = re.compile(r"^(?:京东超市|天猫超市)\s*")


def _paid_amount(doc: EvidenceText) -> Money | None:
    value = value_after(doc, PAID_LABEL)
    if "合计" in value:
        total = find_money(value.split("合计", 1)[1])
        if total:
            return total
    amounts = find_all_money(value)
    return amounts[-1] if amounts else find_money(value_after(doc, "合计"))


def _store(doc: EvidenceText) -> tuple[int, str]:
    for index, line in enumerate(doc.lines[:STORE_SCAN_LINES]):
        for box in line.boxes:
            if STORE_RE.search(box.text):
                return index, STORE_NOISE_RE.sub("", box.text).strip()
    if not doc.lines:
        return -1, ""
    return 0, STORE_NOISE_RE.sub("", doc.lines[0].text).strip()


def _candidates(line: TextLine) -> list[str]:
    return [
        box.text for box in line.boxes if box.text not in ITEM_NOISE and not find_money(box.text)
    ]


def _clean_item(text: str) -> str:
    return PLATFORM_PREFIX_RE.sub("", ELLIPSIS_RE.sub("", text)).strip(" -_")


def _item_name(doc: EvidenceText, store_index: int) -> str:
    """商品名：店铺行与实付款行之间首个被截断（“...”）的标题，否则店铺下一行最长文本。"""
    paid_line = find_line(doc, PAID_LABEL)
    stop = paid_line if paid_line > store_index else len(doc.lines)
    product_lines = doc.lines[store_index + 1 : stop]
    for line in product_lines:
        truncated = [text for text in _candidates(line) if ELLIPSIS_RE.search(text)]
        if truncated:
            return _clean_item(truncated[0])
    first = _candidates(product_lines[0]) if product_lines else []
    return _clean_item(max(first, key=len)) if first else ""


def _occurred_on(doc: EvidenceText):
    for label in PAY_TIME_LABELS:
        found = parse_date(value_after(doc, label))
        if found:
            return found
    return parse_date(doc.text)


def recognize(doc: EvidenceText) -> RecognizedEvidence | None:
    score = feature_score(doc, FEATURES)
    if score < MIN_SCORE:
        return None
    store_index, store = _store(doc)
    return build(
        NAME,
        DOC_ORDER,
        score,
        occurred_on=_occurred_on(doc),
        merchant=store,
        item_name=_item_name(doc, store_index),
        order_no=first_digits(value_after(doc, r"订单编号|订单号")),
        **money_fields(_paid_amount(doc)),
    )
