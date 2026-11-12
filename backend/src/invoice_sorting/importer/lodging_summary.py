"""住宿组摘要（差旅住宿凭证设计第 3 节）：金额为组内全部发票合计，商家为酒店名，分类为差旅交通。"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.db.models import Category
from invoice_sorting.importer.items import EvidenceItem
from invoice_sorting.importer.lodging import merge_stays

TRAVEL_CATEGORY = "差旅交通"


@dataclass(frozen=True)
class LodgingSummary:
    spent_on: date | None
    amount_cents: int | None
    merchant: str
    summary: str
    category_id: int | None


def invoice_total(items: Sequence[EvidenceItem]) -> int | None:
    amounts = [item.cny_cents for item in items if item.is_invoice and item.cny_cents is not None]
    return sum(amounts) if amounts else None


def _transport_key(item: EvidenceItem) -> tuple | int:
    number = item.detail("number")
    route = tuple(part.strip() for part in item.route)
    if number or any(route):
        return (item.travel_date, item.detail("vehicle"), number, route)
    if item.order_key:
        return ("order", item.order_key)
    return item.attachment_id


def transport_total(items: Sequence[EvidenceItem]) -> int:
    """同一段行程的发票、订单、行程单只计一次，优先采用发票金额。"""
    grouped: dict[tuple | int, list[EvidenceItem]] = {}
    for item in items:
        if item.is_transport and item.cny_cents is not None:
            grouped.setdefault(_transport_key(item), []).append(item)
    total = 0
    for matches in grouped.values():
        preferred = next((item for item in matches if item.is_invoice), matches[0])
        total += preferred.cny_cents or 0
    return total


def travel_package_total(items: Sequence[EvidenceItem]) -> int | None:
    """住宿服务 + 去返程/市内交通的净额；订单与其对应发票不重复累计。"""
    if merge_stays(items) is None:
        return None
    lodging_invoices = [
        item.cny_cents
        for item in items
        if item.is_lodging_invoice and item.cny_cents is not None
    ]
    if lodging_invoices:
        lodging = sum(lodging_invoices)
    else:
        lodging = next(
            (
                item.cny_cents
                for item in items
                if item.is_hotel_order and item.cny_cents is not None
            ),
            0,
        )
    total = lodging + transport_total(items)
    return total if total > 0 else None


def _hotel(items: Sequence[EvidenceItem]) -> str:
    orders = [item.hotel_name for item in items if item.is_hotel_order and item.hotel_name]
    invoices = [item.merchant for item in items if item.is_lodging_invoice and item.merchant]
    return next(iter(orders + invoices), "")


def _nights(items: Sequence[EvidenceItem]) -> int | None:
    for item in items:
        if not item.is_hotel_order:
            continue
        nights = item.detail("nights")
        if nights.isdigit() and int(nights) > 0:
            return int(nights)
        stay = item.stay
        if stay is not None and stay.check_in and stay.check_out > stay.check_in:
            return (stay.check_out - stay.check_in).days
    return None


def transport_count(items: Sequence[EvidenceItem]) -> int:
    """交通票张数：同一日期、同一车次/线路的发票与订单截图只算一张。"""
    keys = set()
    for item in items:
        if not item.is_transport:
            continue
        number = item.detail("number") or "-".join(item.route).strip("-")
        keys.add((item.travel_date, number) if number else item.attachment_id)
    return len(keys)


def _summary_text(hotel: str, nights: int | None, transports: int) -> str:
    text = hotel or "住宿"
    if nights:
        text += f" {nights}晚"
    if transports:
        text += f" + 交通 {transports} 张"
    return text


def _travel_category(session: Session) -> int | None:
    query = select(Category.id).where(
        Category.name == TRAVEL_CATEGORY, Category.archived.is_(False)
    )
    return session.scalar(query)


def lodging_summary(session: Session, items: Sequence[EvidenceItem]) -> LodgingSummary | None:
    """组内有酒店订单或住宿发票时返回住宿组摘要，否则 None。"""
    stay = merge_stays(items)
    if stay is None:
        return None
    hotel = _hotel(items)
    fallback_day = next(
        (
            item.association_date
            for item in items
            if not item.is_invoice and item.association_date is not None
        ),
        None,
    ) or next(
        (item.association_date for item in items if item.association_date is not None),
        None,
    ) or next(
        (item.occurred_on for item in items if item.is_lodging_invoice and item.occurred_on),
        None,
    )
    return LodgingSummary(
        spent_on=stay.check_in or fallback_day,
        amount_cents=travel_package_total(items),
        merchant=hotel,
        summary=_summary_text(hotel, _nights(items), transport_count(items)),
        category_id=_travel_category(session),
    )
