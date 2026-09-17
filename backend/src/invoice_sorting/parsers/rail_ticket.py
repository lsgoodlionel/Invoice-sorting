"""铁路电子客票 PDF 解析器。"""

import re
from pathlib import Path

from invoice_sorting.parsers.base import ParsedInvoice
from invoice_sorting.parsers.pdf_text import pdf_text_for_detection
from invoice_sorting.parsers.text_utils import (
    AMOUNT,
    DATE_PATTERN,
    compact,
    find_invoice_no,
    find_labeled_date,
    make_date,
    normalize_text,
    search_group,
    spaced,
    to_cents,
)
from invoice_sorting.parsers.travel_common import (
    TravelFields,
    build_travel_invoice,
    pdf_text_or_raise,
)

STATION = r"([一-鿿]{1,12}?)\s*站"
TRAIN = r"([GDCZTKLYS]?\d{1,5})"
ROUTE_RE = re.compile(STATION + r"\s+" + TRAIN + r"\s+" + STATION)
DEPARTURE_RE = re.compile(DATE_PATTERN + r"\s*\d{1,2}:\d{2}\s*开")
FARE_RE = re.compile(spaced("票价") + r"\s*:?\s*¥?\s*(" + AMOUNT + ")")
YUAN_RE = re.compile(r"¥\s*(" + AMOUNT + ")")
PASSENGER_RE = re.compile(r"\d{6,10}\*{2,}\d{2,4}[\dXx]?\s+([一-鿿·]{2,20})")
DEFAULT_SELLER = "中国铁路"


def _travel_date(text: str) -> str:
    match = DEPARTURE_RE.search(text)
    if not match:
        return ""
    departure = make_date(*match.groups())
    return departure.isoformat() if departure else ""


def _fare_cents(text: str) -> int | None:
    fare = search_group(FARE_RE.pattern, text) or search_group(YUAN_RE.pattern, text)
    return to_cents(fare)


def _invoice_type(text: str) -> str:
    return "电子发票（铁路电子客票）" if "电子发票" in compact(text) else "铁路电子客票"


class RailTicketParser:
    name = "rail_ticket"

    def can_parse(self, path: Path, text: str | None) -> bool:
        content = pdf_text_for_detection(path, text)
        if not content:
            return False
        flat = compact(content)
        return "电子客票" in flat and "铁路" in flat and "行程单" not in flat

    def parse(self, path: Path, text: str | None) -> ParsedInvoice:
        raw_text = pdf_text_or_raise(path, text)
        normalized = normalize_text(raw_text)
        route = ROUTE_RE.search(normalized)
        fields = TravelFields(
            invoice_no=find_invoice_no(normalized),
            issued_on=find_labeled_date(("开票日期",), normalized),
            total_cents=_fare_cents(normalized),
            seller_name=DEFAULT_SELLER if DEFAULT_SELLER in compact(raw_text) else "",
            invoice_type=_invoice_type(raw_text),
            date=_travel_date(normalized),
            origin=route.group(1) if route else "",
            destination=route.group(3) if route else "",
            passenger=search_group(PASSENGER_RE.pattern, normalized) or "",
            train_or_flight=route.group(2) if route else "",
        )
        return build_travel_invoice(fields, raw_text, self.name)
