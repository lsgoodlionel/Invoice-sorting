"""住宿记录的匹配加分（差旅住宿凭证设计第 4 节），供 M3 评分使用。

- 住宿记录（有酒店订单或住宿发票）↔ 新上传交通凭证：日期在入住前后 1 天内且城市匹配 → +60；
- 住宿发票 ↔ “只有订单”的记录：金额相同 + 酒店名匹配 + 日期窗口 → +70。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from invoice_sorting.db.models import Expense
from invoice_sorting.importer.items import EvidenceItem, item_from_attachment
from invoice_sorting.importer.lodging import (
    invoice_matches_order,
    merge_stays,
    stay_label,
    transport_fits,
    with_fallback_day,
)

SCORE_TRANSPORT = 60
SCORE_LODGING_INVOICE = 70
REASON_LODGING_INVOICE = "酒店发票与订单一致"
MAX_STAY_DAYS = 30  # 候选池：交通日期之前 30 天内入住的记录


@dataclass(frozen=True)
class LodgingScore:
    parts: tuple[tuple[int, str], ...] = ()
    joins_transport: bool = False  # 交通凭证并入住宿记录：不按“已有发票/交通凭证”扣分


def _order_only(existing: Sequence[EvidenceItem]) -> list[EvidenceItem]:
    if any(item.is_invoice for item in existing):
        return []
    return [item for item in existing if item.is_hotel_order]


def lodging_score(items: Sequence[EvidenceItem], expense: Expense) -> LodgingScore:
    existing = [item_from_attachment(attachment) for attachment in expense.attachments]
    stay = merge_stays(existing)
    if stay is None:
        return LodgingScore()
    stay = with_fallback_day(stay, expense.spent_on)
    parts: list[tuple[int, str]] = []
    joins = any(transport_fits(item, stay) for item in items)
    if joins:
        parts.append((SCORE_TRANSPORT, stay_label(stay)))
    orders = _order_only(existing)
    invoices = [item for item in items if item.is_lodging_invoice]
    if any(invoice_matches_order(invoice, order) for invoice in invoices for order in orders):
        parts.append((SCORE_LODGING_INVOICE, REASON_LODGING_INVOICE))
    return LodgingScore(tuple(parts), joins)


def transport_window(items: Sequence[EvidenceItem]) -> tuple[date, date] | None:
    """新交通凭证可能属于的住宿记录的支出日期范围（用于扩大候选池）。"""
    days = [item.travel_date for item in items if item.is_transport and item.travel_date]
    if not days:
        return None
    return min(days) - timedelta(days=MAX_STAY_DAYS), max(days) + timedelta(days=1)
