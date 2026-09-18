"""交通凭证字段：交通工具、出发/到达地、车次/航班号、出发日期、乘客。"""

import re
from dataclasses import dataclass
from datetime import date

from invoice_sorting.evidence.lines import EvidenceText
from invoice_sorting.evidence.recognizers.travel_text import (
    find_date,
    first_labeled,
    labeled_date,
    year_hint,
)

VEHICLE_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "train",
        ("12306", "车次", "铁路", "高铁", "动车", "火车", "席别", "二等座", "一等座")
        + ("商务座", "硬卧", "软卧", "硬座", "检票口"),
    ),
    ("flight", ("航班", "起飞", "乘机", "机票", "登机", "经济舱", "头等舱", "公务舱", "航空")),
    ("bus", ("汽车票", "客运站", "客运总站", "汽车站", "巴士", "班次", "长途汽车", "大巴")),
    ("ship", ("船票", "码头", "船名", "乘船", "轮渡", "客轮", "开航", "航次", "港")),
)
FROM_LABELS = (r"出发站|出发地|出发城市|始发站|出发机场|出发港|上车站|起点站|起点|出发(?![时日])",)
TO_LABELS = (r"到达站|到达地|到达城市|终点站|到达机场|到达港|下车站|目的地|终点|到达(?![时日])",)
NUMBER_LABELS = (r"航班号|航班|车次|班次|船次|航次|船名",)
DATE_LABEL = (
    r"发车时间|出发时间|出发日期|乘车日期|乘车时间|开车时间|起飞时间|起飞日期|航班日期"
    r"|开航时间|开船时间|乘船日期|出行日期"
)
PASSENGER_LABELS = (r"乘车人|乘机人|乘船人|乘客姓名|旅客姓名|乘客|旅客|出行人",)
PLACE = r"[一-鿿]{2,16}"
PLACE_RE = re.compile(PLACE)
CODE = r"[A-Z]{1,2}\d{1,5}|\d[A-Z]\d{3,4}"
ARROW_RE = re.compile(
    rf"({PLACE})[A-Za-z0-9]{{0,3}}\s*(?:→|->|—>|⇀|至|到(?!达)|—|－|~|-)\s*({PLACE})"
)
SANDWICH_RE = re.compile(rf"({PLACE})\s+({CODE})\s+({PLACE})")
TRAIN_RE = re.compile(r"(?<![A-Za-z0-9])([GDC]\d{1,4}|[ZTKLYS]\d{2,4})(?![A-Za-z0-9])")
FLIGHT_RE = re.compile(r"(?<![A-Z0-9])((?:[A-Z]{2}|[A-Z]\d|\d[A-Z])\d{3,4})(?![A-Z0-9])")
TOKEN_RE = re.compile(r"[^\s,，;；:：]{1,12}")
TIME_RE = re.compile(r"\d{1,2}:\d{2}")
NOT_DEPARTURE_RE = re.compile(r"下单|订单|支付|付款|创建|购票|出票")
PLACE_SUFFIXES = ("国际机场", "机场", "火车站", "客运码头", "码头", "港")
TRAIN_SUFFIX = "站"


@dataclass(frozen=True)
class Route:
    origin: str = ""
    destination: str = ""
    number: str = ""


def vehicle_of(text: str) -> str:
    """特征词命中最多的交通工具；都不命中为 ""。"""
    counts = [(sum(word in text for word in words), name) for name, words in VEHICLE_WORDS]
    best = max(counts, key=lambda item: item[0])
    return best[1] if best[0] > 0 else ""


def _clean_place(place: str, vehicle: str) -> str:
    for suffix in PLACE_SUFFIXES:
        if place.endswith(suffix) and len(place) > len(suffix) + 1:
            return place[: -len(suffix)]
    if vehicle == "train" and place.endswith(TRAIN_SUFFIX) and len(place) > 2:
        return place[:-1]
    return place


def _first_place(value: str) -> str:
    match = PLACE_RE.search(value)
    return match.group(0) if match else ""


def _raw_route(doc: EvidenceText) -> Route:
    origin = _first_place(first_labeled(doc, FROM_LABELS))
    destination = _first_place(first_labeled(doc, TO_LABELS))
    if origin and destination:
        return Route(origin, destination)
    for line in doc.lines:
        arrow = ARROW_RE.search(line.text)
        if arrow:
            return Route(arrow.group(1), arrow.group(2))
    for line in doc.lines:
        sandwich = SANDWICH_RE.search(line.text)
        if sandwich:
            return Route(sandwich.group(1), sandwich.group(3), sandwich.group(2))
    return Route()


def route_of(doc: EvidenceText, vehicle: str) -> Route:
    raw = _raw_route(doc)
    return Route(
        _clean_place(raw.origin, vehicle), _clean_place(raw.destination, vehicle), raw.number
    )


def number_of(doc: EvidenceText, vehicle: str, route: Route) -> str:
    """车次/航班号/班次/船名：标签值优先，其次路线中间的编号，再按交通工具正则。"""
    token = TOKEN_RE.match(first_labeled(doc, NUMBER_LABELS).strip())
    if token:
        return token.group(0)
    if route.number:
        return route.number
    pattern = {"train": TRAIN_RE, "flight": FLIGHT_RE}.get(vehicle)
    found = pattern.search(doc.text) if pattern else None
    return found.group(1) if found else ""


def _departure_line_date(doc: EvidenceText, year: int) -> date | None:
    for line in doc.lines:
        text = line.text
        if TIME_RE.search(text) and not NOT_DEPARTURE_RE.search(text):
            found = find_date(text, year)
            if found:
                return found
    return None


def travel_date(doc: EvidenceText) -> date | None:
    """出发日期：日期标签 → 带时刻的非下单行 → 文中第一个日期。"""
    year = year_hint(doc)
    return (
        labeled_date(doc, DATE_LABEL, year)
        or _departure_line_date(doc, year)
        or find_date(doc.text, year)
    )


def passenger_value(doc: EvidenceText) -> str:
    return first_labeled(doc, PASSENGER_LABELS)
