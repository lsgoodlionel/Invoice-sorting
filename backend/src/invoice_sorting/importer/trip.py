"""从实际交通路线和住宿区间推导一次差旅；开票地区不代表入住地。"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from invoice_sorting.importer.cities import find_city, normalize_city
from invoice_sorting.importer.items import EvidenceItem
from invoice_sorting.importer.lodging import invoice_matches_order, merge_stays


def route_city(place: str) -> str:
    return normalize_city(find_city(place))


@dataclass(frozen=True)
class Trip:
    destination: str
    start: date | None
    end: date | None
    outbound: tuple[int, ...]
    returning: tuple[int, ...]
    outbound_legs: int
    return_legs: int
    lodging_nights: int
    expected_nights: int | None
    warnings: tuple[str, ...]

    @property
    def name(self) -> str:
        if self.start is None or self.end is None:
            return ""
        destination = self.destination or "待确认地区"
        return f"{self.start:%Y年%m月%d日}-{self.end:%Y年%m月%d日}{destination}差旅"


def trip_from_items(items: Sequence[EvidenceItem], local_region: str = "") -> Trip | None:
    stay = merge_stays(items)
    local = normalize_city(local_region)
    routes = [
        (item, route_city(item.route[0]), route_city(item.route[1]))
        for item in items
        if item.is_transport and item.travel_date and all(item.route)
    ]
    destination = stay.city if stay else ""
    if not destination and local:
        destinations = {end for _, origin, end in routes if origin == local and end != local}
        destinations.update(origin for _, origin, end in routes if end == local and origin != local)
        if len(destinations) == 1:
            destination = destinations.pop()
    if not destination and stay is None:
        return None
    destination = normalize_city(destination)
    outbound = tuple(
        item.attachment_id
        for item, origin, end in routes
        if end == destination and origin != destination and (not local or origin == local)
    )
    returning = tuple(
        item.attachment_id
        for item, origin, end in routes
        if origin == destination and end != destination and (not local or end == local)
    )

    def leg_count(ids: tuple[int, ...]) -> int:
        return len(
            {
                (item.travel_date, item.detail("vehicle"), item.detail("number"), origin, end)
                for item, origin, end in routes
                if item.attachment_id in ids
            }
        )

    outbound_legs = leg_count(outbound)
    return_legs = leg_count(returning)
    departures = [
        item.travel_date for item, origin, end in routes if item.attachment_id in outbound
    ]
    arrivals = [item.travel_date for item, origin, end in routes if item.attachment_id in returning]
    start = min(departures) if departures else (stay.check_in if stay else None)
    end = max(arrivals) if arrivals else (stay.check_out if stay else None)
    if end is None:
        end = start
    if start is None:
        start = end
    orders = [item for item in items if item.is_hotel_order and item.stay]
    invoices = [item for item in items if item.is_lodging_invoice]
    nights: set[date] = set()
    for order in orders:
        period = order.stay
        if period and period.check_in and period.check_out:
            nights.update(
                date.fromordinal(day)
                for day in range(period.check_in.toordinal(), period.check_out.toordinal())
            )
    # 无订单但发票明确写了入住日期时，才把该发票算作住宿天数。
    for invoice in invoices:
        if any(invoice_matches_order(invoice, order) for order in orders):
            continue
        period = invoice.stay
        if period and period.check_in and period.check_out:
            nights.update(
                date.fromordinal(day)
                for day in range(period.check_in.toordinal(), period.check_out.toordinal())
            )
    expected = max(0, (end - start).days) if start and end else None
    warnings: list[str] = []
    if not destination:
        warnings.append("住宿地点待确认：请补充酒店订单或水单")
    if not outbound and not returning:
        warnings.append("待补充往返交通凭证")
    else:
        if not outbound:
            warnings.append("待补充去程交通凭证")
        if not returning:
            warnings.append("待补充返程交通凭证")
    if outbound_legs > 1:
        warnings.append(f"去程交通识别到 {outbound_legs} 段，请核对是否属于同一次差旅")
    if return_legs > 1:
        warnings.append(f"返程交通识别到 {return_legs} 段，请核对是否属于同一次差旅")
    if expected is not None and len(nights) < expected:
        warnings.append(f"住宿记录不足：预计 {expected} 晚，已识别 {len(nights)} 晚")
    if expected is not None and len(nights) > expected:
        warnings.append(f"住宿记录多于行程：预计 {expected} 晚，已识别 {len(nights)} 晚，请核对")
    if stay and stay.check_in is None:
        warnings.append("住宿时间待完善：请补充酒店订单或水单")
    return Trip(
        destination,
        start,
        end,
        outbound,
        returning,
        outbound_legs,
        return_legs,
        len(nights),
        expected,
        tuple(warnings),
    )
