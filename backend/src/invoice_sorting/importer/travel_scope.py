"""交通住宿凭证的“市内/市外”识别。结果存到支出记录，允许用户手工纠正。"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from invoice_sorting.common.constants import TravelScope
from invoice_sorting.db.models import AppSetting, Attachment, Expense
from invoice_sorting.importer.cities import find_city, normalize_city
from invoice_sorting.importer.items import EvidenceItem, item_from_attachment
from invoice_sorting.importer.lodging import merge_stays


def _place_city(place: str) -> str:
    return normalize_city(find_city(place) or place)


def _against_local(cities: set[str], local_region: str) -> str:
    local = normalize_city(local_region)
    if not cities:
        return ""
    if len(cities) > 1:
        return str(TravelScope.NONLOCAL)
    if not local:
        return ""
    only = next(iter(cities))
    return str(TravelScope.LOCAL if only == local else TravelScope.NONLOCAL)


def infer_travel_scope(items: Sequence[EvidenceItem], local_region: str) -> str:
    """路线跨城即市外；单城交通/住宿与“本地地区”比较，无法定位时留空。"""
    all_cities: set[str] = set()
    has_travel = False
    stay = merge_stays(items)
    if stay is not None:
        has_travel = True
        city = normalize_city(stay.city)
        if city:
            all_cities.add(city)
    for item in items:
        if not item.is_transport:
            continue
        has_travel = True
        route_cities = {_place_city(place) for place in item.route if place}
        route_cities.discard("")
        if len(route_cities) > 1:
            return str(TravelScope.NONLOCAL)
        all_cities.update(route_cities)
        city = normalize_city(item.detail("city"))
        if city:
            all_cities.add(city)
    return _against_local(all_cities, local_region) if has_travel else ""


def infer_expense_travel_scope(expense: Expense, local_region: str) -> str:
    items = [item_from_attachment(attachment) for attachment in expense.attachments]
    return infer_travel_scope(items, local_region)


BACKFILL_KEY = "travel_scope_backfill_version"
BACKFILL_VERSION = "1"


def backfill_travel_scopes(session: Session, local_region: str) -> int:
    """升级后一次性补算历史记录；手工设置过的记录不覆盖。"""
    marker = session.get(AppSetting, BACKFILL_KEY)
    if marker is not None and marker.value == BACKFILL_VERSION:
        return 0
    query = (
        select(Expense)
        .where(Expense.deleted.is_(False), Expense.travel_scope_manual.is_(False))
        .options(
            selectinload(Expense.attachments).selectinload(Attachment.invoice_data),
            selectinload(Expense.attachments).selectinload(Attachment.evidence_data),
        )
        .order_by(Expense.id)
    )
    changed = 0
    for expense in session.scalars(query):
        scope = infer_expense_travel_scope(expense, local_region)
        if scope != expense.travel_scope:
            expense.travel_scope = scope
            changed += 1
    session.merge(AppSetting(key=BACKFILL_KEY, value=BACKFILL_VERSION))
    session.commit()
    return changed
