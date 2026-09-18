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


def _amount(items: Sequence[EvidenceItem]) -> int | None:
    """有发票取发票合计（订单不计）；只有订单时取订单人民币金额。"""
    total = invoice_total(items)
    if total is not None:
        return total
    return next((i.cny_cents for i in items if i.is_hotel_order and i.cny_cents is not None), None)


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
    return LodgingSummary(
        spent_on=stay.check_in or next((i.occurred_on for i in items if i.occurred_on), None),
        amount_cents=_amount(items),
        merchant=hotel,
        summary=_summary_text(hotel, _nights(items), transport_count(items)),
        category_id=_travel_category(session),
    )
