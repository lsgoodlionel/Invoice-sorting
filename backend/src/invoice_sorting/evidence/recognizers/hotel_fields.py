"""酒店订单：酒店名与所在城市（“城市 - 酒店名”行、标签、地址）。"""

import re

from invoice_sorting.evidence.lines import EvidenceText
from invoice_sorting.evidence.recognizers.travel_text import first_labeled
from invoice_sorting.parsers.regions import PROVINCES

HOTEL_WORD = (
    r"酒店|宾馆|饭店|旅馆|客栈|民宿|公寓|度假村|hotel|inn\b|resort|hostel|suites?\b|lodge|motel"
)
HOTEL_WORD_RE = re.compile(HOTEL_WORD, re.IGNORECASE)
CITY_HOTEL_RE = re.compile(r"^([一-鿿]{2,8})\s*[-－—–]\s*(\S.{1,60})$")
HOTEL_LABELS = (r"酒店名称|酒店名|hotel\s*name|property\s*name|accommodation",)
CITY_LABELS = (r"(?<![a-z])city(?![a-z])|所在城市|城市",)
ADDRESS_LABELS = (r"酒店地址|地址|address",)
NOT_NAME_RE = re.compile(
    r"酒店(?:电话|地址|类型|确认号|提供|政策)|须知|政策|[,，。:：!！?？]"
    r"|^(?:美团|携程|飞猪|去哪儿|同程|艺龙)(?:酒店|民宿)$"
)
MAX_NAME_CHARS = 60
MUNICIPALITIES = ("北京", "上海", "天津", "重庆")
PROVINCE_PREFIX_RE = re.compile(
    "^(?:" + "|".join(PROVINCES.values()) + r")(?:省|(?:壮族|回族|维吾尔)?自治区)?"
)
CITY_SUFFIX_RE = re.compile(r"^([一-鿿]{2,5}?)市")
CITY_TOKEN_RE = re.compile(r"^([一-鿿]{2,4})\s")
CJK_CITY_RE = re.compile(r"^[一-鿿]{2,8}$")
LATIN_CITY_RE = re.compile(r"^[A-Za-z][A-Za-z .'-]{1,30}$")


def _city_hotel_line(doc: EvidenceText) -> tuple[str, str]:
    for line in doc.lines:
        match = CITY_HOTEL_RE.match(line.text.strip())
        if match and HOTEL_WORD_RE.search(match.group(2)):
            return match.group(2).strip(), match.group(1)
    return "", ""


def _looks_like_name(text: str) -> bool:
    has_word = HOTEL_WORD_RE.search(text) is not None
    return has_word and len(text) <= MAX_NAME_CHARS and not NOT_NAME_RE.search(text)


def _hotel_name(doc: EvidenceText) -> str:
    labeled = first_labeled(doc, HOTEL_LABELS)
    if labeled:
        return labeled[:MAX_NAME_CHARS]
    return next((line.text.strip() for line in doc.lines if _looks_like_name(line.text)), "")


def city_from_address(address: str) -> str:
    """地址中的城市：直辖市前缀、“XX市”，或省名之后的两个字；无法判断为 ""。"""
    text = address.strip()
    token = CITY_TOKEN_RE.match(text)
    if token:
        return token.group(1)
    municipality = next((name for name in MUNICIPALITIES if text.startswith(name)), "")
    if municipality:
        return municipality
    stripped = PROVINCE_PREFIX_RE.sub("", text)
    city = CITY_SUFFIX_RE.match(stripped)
    if city:
        return city.group(1)
    return stripped[:2] if stripped != text and CJK_CITY_RE.match(stripped[:2]) else ""


def _labeled_city(doc: EvidenceText) -> str:
    value = first_labeled(doc, CITY_LABELS).strip()
    if CJK_CITY_RE.match(value) or LATIN_CITY_RE.match(value):
        return value
    return ""


def hotel_and_city(doc: EvidenceText) -> tuple[str, str]:
    """(酒店名, 城市)；“苏州 - 某某酒店”行优先，其次标签与启发式。"""
    hotel, city = _city_hotel_line(doc)
    if not hotel:
        hotel = _hotel_name(doc)
    if not city:
        city = _labeled_city(doc) or city_from_address(first_labeled(doc, ADDRESS_LABELS))
    return hotel, city
