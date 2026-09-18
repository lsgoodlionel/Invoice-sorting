"""住宿差旅凭证的纯函数规则（差旅住宿凭证设计第 3、4 节）：

- 酒店发票 ↔ 酒店订单是否一致（L6 / 住宿发票匹配“只有订单”的记录）；
- 一组凭证的住宿区间与城市；
- 交通凭证是否往返酒店所在地（L7 / 住宿记录匹配新交通凭证）；
- 一组内允许的发票组合：一张住宿发票 + 任意交通票发票。
"""

import re
from collections.abc import Sequence
from dataclasses import replace
from datetime import date, timedelta

from invoice_sorting.importer.cities import COMMON_CITIES, place_in_city
from invoice_sorting.importer.items import EvidenceItem, Stay
from invoice_sorting.importer.merchants import longest_common_substring

STAY_MARGIN = timedelta(days=1)  # 交通日期可在入住前 1 天、离店后 1 天
INVOICE_AFTER_CHECKOUT = timedelta(days=30)  # 酒店发票可在离店后 30 天内开具
MIN_COMMON_HOTEL_CHARS = 2
GENERIC_HOTEL_WORDS = re.compile(
    "|".join(
        (
            "有限责任公司",
            "股份有限公司",
            "有限公司",
            "分公司",
            "公司",
            "管理",
            "集团",
            "酒店",
            "宾馆",
            "饭店",
            "旅馆",
            "民宿",
            "客栈",
            *COMMON_CITIES,
        )
    )
)
WHITESPACE = re.compile(r"\s+")


def _hotel_core(name: str) -> str:
    """去掉城市、公司后缀与“酒店”等通用词，只留品牌/店名部分。"""
    return GENERIC_HOTEL_WORDS.sub("", WHITESPACE.sub("", name or ""))


def hotel_names_match(first: str, second: str) -> bool:
    """酒店名与销售方名称有 ≥2 字公共子串（不计城市与通用词）。"""
    common = longest_common_substring(_hotel_core(first), _hotel_core(second))
    return common >= MIN_COMMON_HOTEL_CHARS


def _issued_in_window(issued: date | None, stay: Stay | None) -> bool:
    if issued is None or stay is None or stay.check_in is None:
        return False
    check_out = stay.check_out or stay.check_in
    return stay.check_in <= issued <= check_out + INVOICE_AFTER_CHECKOUT


def invoice_matches_order(invoice: EvidenceItem, order: EvidenceItem) -> bool:
    """人民币金额相同 + 酒店名匹配 + 开票日期在入住日期至离店后 30 天内。"""
    if not (invoice.is_lodging_invoice and order.is_hotel_order):
        return False
    if invoice.cny_cents is None or invoice.cny_cents != order.cny_cents:
        return False
    if not hotel_names_match(invoice.merchant, order.hotel_name):
        return False
    return _issued_in_window(invoice.occurred_on, order.stay)


def merge_stays(items: Sequence[EvidenceItem]) -> Stay | None:
    """订单的入住/离店优先（多张订单取最早入住、最晚离店），无订单日期时取住宿发票开票日期。"""
    orders = [item.stay for item in items if item.is_hotel_order]
    invoices = [item.stay for item in items if item.is_lodging_invoice]
    stays = [stay for stay in orders + invoices if stay is not None]
    if not stays:
        return None
    dated = [stay for stay in orders if stay is not None and stay.check_in] or stays
    check_ins = [stay.check_in for stay in dated if stay.check_in]
    check_outs = [stay.check_out or stay.check_in for stay in dated if stay.check_in]
    city = next((stay.city for stay in stays if stay.city), "")
    if not check_ins:
        return Stay(None, None, city)
    return Stay(min(check_ins), max(check_outs), city)


def with_fallback_day(stay: Stay, fallback: date | None) -> Stay:
    """没有任何日期时用记录的支出日期作入住/离店日期。"""
    if stay.check_in is not None or fallback is None:
        return stay
    return replace(stay, check_in=fallback, check_out=fallback)


def transport_fits(item: EvidenceItem, stay: Stay | None) -> bool:
    """交通日期在 [入住−1, 离店+1] 内，且起点或终点在酒店所在城市。"""
    if stay is None or not stay.city or stay.check_in is None or not item.is_transport:
        return False
    day = item.travel_date
    check_out = stay.check_out or stay.check_in
    if day is None or not stay.check_in - STAY_MARGIN <= day <= check_out + STAY_MARGIN:
        return False
    return any(place_in_city(place, stay.city) for place in item.route)


def invoices_compatible(items: Sequence[EvidenceItem]) -> bool:
    """每组最多一张发票；住宿组（有住宿发票或酒店订单）可再有任意张交通票发票。"""
    invoices = [item for item in items if item.is_invoice]
    if len(invoices) <= 1:
        return True
    lodging = [item for item in invoices if item.is_lodging_invoice]
    if len(lodging) > 1:
        return False
    has_lodging = bool(lodging) or any(item.is_hotel_order for item in items)
    others = [item for item in invoices if not item.is_lodging_invoice]
    return has_lodging and all(item.is_transport for item in others)


def stay_label(stay: Stay) -> str:
    """“往返 苏州 的交通凭证（入住 08-15、离店 08-16）”。"""
    if stay.check_in is None:
        return f"往返 {stay.city} 的交通凭证"
    check_out = stay.check_out or stay.check_in
    dates = f"入住 {stay.check_in:%m-%d}、离店 {check_out:%m-%d}"
    return f"往返 {stay.city} 的交通凭证（{dates}）"
