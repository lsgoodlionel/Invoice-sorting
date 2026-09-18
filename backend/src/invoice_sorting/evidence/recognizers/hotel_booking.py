"""酒店订单确认单（携程/美团/飞猪/同程/Booking.com/Agoda 等）：入住离店、酒店、城市、金额。"""

import re
from datetime import date

from invoice_sorting.evidence.base import DOC_ORDER, RecognizedEvidence
from invoice_sorting.evidence.lines import EvidenceText
from invoice_sorting.evidence.parsing import Money, find_money
from invoice_sorting.evidence.recognizers.common import (
    NO_ANCHOR_CAP,
    Features,
    build,
    feature_score,
    money_fields,
)
from invoice_sorting.evidence.recognizers.hotel_fields import hotel_and_city
from invoice_sorting.evidence.recognizers.travel_text import (
    after,
    compact_details,
    first_labeled,
    labeled_date,
    person_name,
    platform_of,
    year_hint,
)

NAME = "hotel_booking"
PLATFORMS = (
    (r"ctrip\.com|携程", "携程"),
    (r"trip\.com", "Trip.com"),
    (r"meituan|美团", "美团"),
    (r"fliggy|飞猪", "飞猪"),
    (r"(?<![a-z])ly\.com|同程", "同程"),
    (r"elong|艺龙", "艺龙"),
    (r"qunar|去哪儿", "去哪儿"),
    (r"booking\.com", "Booking.com"),
    (r"agoda", "Agoda"),
    (r"expedia", "Expedia"),
    (r"hotels\.com", "Hotels.com"),
    (r"airbnb|爱彼迎", "Airbnb"),
    (r"huazhu|华住", "华住会"),
    (r"jinjiang|锦江", "锦江"),
    (r"atour|亚朵", "亚朵"),
)
FEATURES = Features(
    groups=(
        ("入住日期", "入住时间", "check-in", "checkin", "入住"),
        ("离店日期", "离店时间", "退房", "check-out", "checkout", "离店"),
        ("订单号", "订单编号", "预订号", "确认号", "bookingnumber", "bookingid"),
        ("confirmationnumber", "reservationnumber", "itinerarynumber"),
        ("房型", "房间数量", "间数", "床房", "room"),
        ("入住人", "住客", "guest"),
        ("酒店", "宾馆", "客栈", "民宿", "hotel", "resort", "inn"),
        ("订单确认", "预订确认", "确认单", "预订成功", "confirmation"),
        ("晚", "night"),
        ("订单金额", "总价", "在线支付", "实付", "房费", "total"),
        tuple(
            ("携程", "ctrip", "trip.com", "美团", "meituan", "飞猪", "fliggy", "同程", "ly.com")
            + ("艺龙", "去哪儿", "qunar", "booking.com", "agoda", "expedia", "华住", "锦江")
            + ("亚朵", "airbnb")
        ),
    ),
    needed=5,
    anchors=("入住", "离店", "退房", "check-in", "check-out", "checkin", "checkout"),
)
ORDER_LABELS = (
    r"订单号|订单编号|预订单号|预订号",
    r"(?:booking|confirmation|reservation|itinerary)\s*(?:number|no\.?|id|reference)"
    r"|order\s*(?:id|number|no\.?)",
)
AMOUNT_LABELS = (
    r"订单金额|订单总额|房费总额|总金额|总价|应付金额|实付金额|实付款|实付|在线支付|支付金额",
    r"total\s*(?:price|amount|charge|cost)|amount\s*paid|grand\s*total|total",
)
CHECK_IN_LABEL = r"入住日期|入住时间|入住(?!人)|check[\s-]*in"
CHECK_OUT_LABEL = r"离店日期|离店时间|退房日期|退房时间|离店|退房|check[\s-]*out"
GUEST_LABELS = (r"入住人(?!数)|住客姓名|入住客人|住客", r"guest\s*name|lead\s*guest|guest")
ROOMS_LABELS = (r"房间数量|房间数|number\s*of\s*rooms",)
ROOMS_RE = re.compile(r"(\d+)\s*(?:间(?!夜)|rooms?\b)", re.IGNORECASE)
NIGHTS_RE = re.compile(r"(\d+)\s*(?:晚|nights?\b)", re.IGNORECASE)
LEADING_INT_RE = re.compile(r"^\s*(\d{1,2})(?!\d)")
REFERENCE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.-]{3,}")


def _order_no(doc: EvidenceText) -> str:
    value = first_labeled(doc, ORDER_LABELS)
    for match in REFERENCE_RE.finditer(value):
        token = match.group(0).rstrip(".-")
        if any(char.isdigit() for char in token):
            return token.replace(".", "")
    return ""


def _amount(doc: EvidenceText) -> Money | None:
    for label in AMOUNT_LABELS:
        money = find_money(first_labeled(doc, (label,)))
        if money:
            return money
    return None


def _stay(doc: EvidenceText) -> tuple[date | None, date | None]:
    year = year_hint(doc)
    check_in = labeled_date(doc, CHECK_IN_LABEL, year)
    check_out = labeled_date(doc, CHECK_OUT_LABEL, year)
    return check_in, after(check_out, check_in)


def _rooms(doc: EvidenceText) -> str:
    match = LEADING_INT_RE.match(first_labeled(doc, ROOMS_LABELS))
    if match:
        return match.group(1)
    found = ROOMS_RE.search(doc.text)
    return found.group(1) if found else ""


def _nights(doc: EvidenceText, check_in: date | None, check_out: date | None) -> str:
    if check_in and check_out and check_out > check_in:
        return str((check_out - check_in).days)
    found = NIGHTS_RE.search(doc.text)
    return found.group(1) if found else ""


def _item_name(details: dict[str, str], check_in: date | None, check_out: date | None) -> str:
    stay = f"{check_in:%m-%d}至{check_out:%m-%d}" if check_in and check_out else ""
    nights = f"{details['nights']}晚" if details.get("nights") else ""
    rooms = f"{details['rooms']}间" if details.get("rooms") else ""
    parts = (details.get("hotel", ""), stay, nights, rooms)
    return " ".join(part for part in parts if part)


def _details(doc: EvidenceText, check_in: date | None, check_out: date | None) -> dict[str, str]:
    hotel, city = hotel_and_city(doc)
    return compact_details(
        {
            "city": city,
            "hotel": hotel,
            "check_in": check_in.isoformat() if check_in else "",
            "check_out": check_out.isoformat() if check_out else "",
            "nights": _nights(doc, check_in, check_out),
            "rooms": _rooms(doc),
            "guest": person_name(first_labeled(doc, GUEST_LABELS)),
            "platform": platform_of(doc.text, PLATFORMS),
        }
    )


def recognize(doc: EvidenceText) -> RecognizedEvidence | None:
    score = feature_score(doc, FEATURES)
    if score <= NO_ANCHOR_CAP:  # 缺少入住/离店锚点或特征太少：不是酒店订单
        return None
    check_in, check_out = _stay(doc)
    details = _details(doc, check_in, check_out)
    return build(
        NAME,
        DOC_ORDER,
        score,
        occurred_on=check_out or check_in,
        merchant=details.get("hotel", ""),
        item_name=_item_name(details, check_in, check_out),
        order_no=_order_no(doc),
        details=details,
        **money_fields(_amount(doc)),
    )
