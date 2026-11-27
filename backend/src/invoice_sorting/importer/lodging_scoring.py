"""住宿记录的匹配加分（差旅住宿凭证设计第 4 节），供 M3 评分使用。

- 住宿记录（有酒店订单或住宿发票）↔ 新上传交通凭证：日期在入住前后 1 天内且城市匹配 → +60；
- 住宿发票 ↔ “只有订单”的记录：金额相同 + 酒店名匹配 + 日期窗口 → +70。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import object_session

from invoice_sorting.db.models import Expense
from invoice_sorting.importer.items import EvidenceItem, item_from_attachment
from invoice_sorting.importer.lodging import (
    invoice_matches_order,
    invoice_order_review_candidate,
    merge_stays,
    stay_label,
    transport_fits,
    with_fallback_day,
)
from invoice_sorting.importer.trip import trip_from_items
from invoice_sorting.settings.service import region_policy

SCORE_TRANSPORT = 60
SCORE_LODGING_INVOICE = 70
REASON_LODGING_INVOICE = "酒店发票与订单一致"
REASON_REVIEW = "待人工确认归属：金额与住宿订单一致，请核对开票单位、入住地点及日期"
MAX_STAY_DAYS = 30  # 候选池：交通日期之前 30 天内入住的记录


@dataclass(frozen=True)
class LodgingScore:
    parts: tuple[tuple[int, str], ...] = ()
    joins_transport: bool = False  # 交通凭证并入住宿记录：不按“已有发票/交通凭证”扣分


def _order_only(existing: Sequence[EvidenceItem]) -> list[EvidenceItem]:
    if any(item.is_lodging_invoice for item in existing):
        return []
    return [item for item in existing if item.is_hotel_order]


def lodging_score(items: Sequence[EvidenceItem], expense: Expense) -> LodgingScore:
    existing = [item_from_attachment(attachment) for attachment in expense.attachments]
    stay = merge_stays(existing)
    if stay is None:
        return _trip_score(items, expense, existing)
    fallback = next(
        (
            item.association_date
            for item in existing
            if not item.is_invoice and item.association_date is not None
        ),
        None,
    )
    stay = with_fallback_day(stay, fallback)
    parts: list[tuple[int, str]] = []
    joins = any(transport_fits(item, stay) for item in items)
    if joins:
        parts.append((SCORE_TRANSPORT, stay_label(stay)))
    orders = _order_only(existing)
    invoices = [item for item in items if item.is_lodging_invoice]
    invoice_join = False
    for invoice in invoices:
        for order in orders:
            if not invoice_order_review_candidate(invoice, order):
                continue
            invoice_join = True
            checkout = order.stay.check_out or order.stay.check_in
            issued = invoice.issued_on or invoice.occurred_on
            strict = invoice_matches_order(invoice, order)
            reason = REASON_REVIEW if issued > checkout or not strict else REASON_LODGING_INVOICE
            parts.append((80 if reason == REASON_REVIEW else SCORE_LODGING_INVOICE, reason))
            break
    trip = _trip_score(items, expense, existing)
    return LodgingScore(tuple(parts) + trip.parts, joins or trip.joins_transport or invoice_join)


def _trip_score(
    items: Sequence[EvidenceItem], expense: Expense, existing: Sequence[EvidenceItem]
) -> LodgingScore:
    session = object_session(expense)
    local = region_policy(session).local_region if session else ""
    trip = trip_from_items(existing, local)
    if trip is None or not trip.destination or trip.start is None:
        return LodgingScore()
    incoming_stay = merge_stays(items)
    if incoming_stay and incoming_stay.city == trip.destination and incoming_stay.check_in:
        day = incoming_stay.check_in
        end = trip.end or trip.start
        if trip.start <= day <= end and (incoming_stay.check_out or day) <= end:
            return LodgingScore(((85, "住宿地点与出差日期一致"),), True)
        if day in (end, end + timedelta(days=1)) and (
            incoming_stay.check_out or day
        ) <= end + timedelta(days=30):
            return LodgingScore(((85, "连续住宿地点一致"),), True)
    # 去程先入库，返程随后上传；必须是同一目的地的反向线路。
    if trip.outbound and not trip.returning:
        from invoice_sorting.importer.cities import place_in_city

        outbound = [item for item in existing if item.attachment_id in trip.outbound]
        for incoming in items:
            if not incoming.is_transport or not incoming.travel_date:
                continue
            if not (trip.start <= incoming.travel_date <= trip.start + timedelta(days=30)):
                continue
            if any(
                place_in_city(incoming.route[0], trip.destination)
                and place_in_city(incoming.route[1], local)
                and place_in_city(previous.route[0], local)
                for previous in outbound
            ):
                return LodgingScore(((85, "同一次差旅的返程线路"),), True)
    return LodgingScore()


def transport_window(items: Sequence[EvidenceItem]) -> tuple[date, date] | None:
    """新交通凭证可能属于的住宿记录的支出日期范围（用于扩大候选池）。"""
    days = [item.travel_date for item in items if item.is_transport and item.travel_date]
    if not days:
        return None
    return min(days) - timedelta(days=MAX_STAY_DAYS), max(days) + timedelta(days=1)
