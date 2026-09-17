"""打车电子行程单（滴滴/享道/高德等）：行程起止日期、共 N 笔行程、合计金额、平台。"""

import re

from invoice_sorting.common.money import yuan_to_cents
from invoice_sorting.evidence.base import DOC_ITINERARY, RecognizedEvidence
from invoice_sorting.evidence.lines import EvidenceText, value_after
from invoice_sorting.evidence.parsing import (
    CNY,
    Money,
    find_all_dates,
    find_money,
    parse_date,
)
from invoice_sorting.evidence.recognizers.common import (
    MIN_SCORE,
    Features,
    build,
    feature_score,
    money_fields,
)

NAME = "ride_itinerary"
PLATFORMS: tuple[tuple[str, str], ...] = (
    ("滴滴", "滴滴出行"),
    ("享道", "享道出行"),
    ("高德", "高德打车"),
    ("曹操", "曹操出行"),
    ("T3出行", "T3出行"),
    ("首汽", "首汽约车"),
    ("美团打车", "美团打车"),
    ("如祺", "如祺出行"),
    ("花小猪", "花小猪打车"),
)
FEATURES = Features(
    groups=(
        ("行程单",),
        ("行程起止日期", "行程时间", "行程日期"),
        ("申请日期", "申请时间", "开具日期"),
        ("笔行程", "个行程"),
        ("上车时间", "下车时间"),
        ("起点", "终点"),
        ("可开票金额", "合计", "总计"),
        ("用车人", "乘车人", "手机号"),
        tuple(key for key, _ in PLATFORMS),
        ("车型", "订单类型", "服务类型", "城市"),
    ),
    needed=4,
    anchors=("行程单", "笔行程", "个行程"),
)
TOTAL_RE = re.compile(r"共\s*(\d+)\s*[笔个]行程[^\d]{0,20}?(\d[\d,]*(?:\.\d{1,2})?)\s*元")
RANGE_LABEL = r"行程(?:起止)?(?:日期|时间)"
APPLY_LABEL = r"申请(?:日期|时间)|开具日期"


def platform_name(text: str) -> str:
    return next((name for key, name in PLATFORMS if key in text), "")


def _total(doc: EvidenceText) -> tuple[Money | None, str]:
    match = TOTAL_RE.search(doc.text)
    if match:
        count, amount = match.groups()
        return Money(yuan_to_cents(amount), CNY), f"共{count}笔行程"
    return find_money(value_after(doc, r"合计|总计")), ""


def _occurred_on(doc: EvidenceText):
    range_dates = find_all_dates(value_after(doc, RANGE_LABEL))
    if range_dates:
        return range_dates[-1]
    return parse_date(value_after(doc, APPLY_LABEL)) or parse_date(doc.text)


def recognize(doc: EvidenceText) -> RecognizedEvidence | None:
    score = feature_score(doc, FEATURES)
    if score < MIN_SCORE:
        return None
    money, item_name = _total(doc)
    return build(
        NAME,
        DOC_ITINERARY,
        score,
        occurred_on=_occurred_on(doc),
        merchant=platform_name(doc.text),
        item_name=item_name,
        **money_fields(money),
    )
