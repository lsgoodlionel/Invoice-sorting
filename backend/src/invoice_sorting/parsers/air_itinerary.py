"""航空运输电子客票行程单 PDF 解析器。"""

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
    labeled,
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

PLACE = r"([一-鿿]{2,12})"
ORIGIN_RE = re.compile(r"(?:^|\s)自\s*(?:FROM)?\s*:?\s*" + PLACE, re.MULTILINE)
DESTINATION_RE = re.compile(r"(?:^|\s)至\s*(?:TO)?\s*:?\s*" + PLACE, re.MULTILINE)
FLIGHT_RE = re.compile(r"(?<![A-Z0-9])((?:[A-Z]{2}|[A-Z]\d|\d[A-Z])\d{3,4})(?![A-Z0-9])")
TOTAL_RE = re.compile(spaced("合计") + r"\s*(?:TOTAL)?\s*:?\s*(?:CNY|¥)?\s*(" + AMOUNT + ")")
PASSENGER_RE = re.compile(
    labeled("旅客姓名") + r"(?:NAME\s*OF\s*PASSENGER)?\s*:?\s*([一-鿿A-Za-z/·]{2,30})"
)
TICKET_NO_RE = re.compile(labeled("电子客票号码") + r"(?:E-TICKET\s*NO\.?)?\s*:?\s*(\d{10,13})")
SELLER_LABELS = ("填开单位", "销售单位")


def _origin_line(text: str) -> str:
    match = ORIGIN_RE.search(text)
    if not match:
        return ""
    line_end = text.find("\n", match.start() + 1)
    return text[match.start() : line_end if line_end != -1 else len(text)]


def _flight_and_date(text: str) -> tuple[str, str]:
    line = _origin_line(text) or text
    flight = FLIGHT_RE.search(line)
    if not flight:
        return "", ""
    date_match = re.search(DATE_PATTERN, line[flight.end() :])
    flown = make_date(*date_match.groups()) if date_match else None
    return flight.group(1), flown.isoformat() if flown else ""


def _seller(text: str) -> str:
    for label in SELLER_LABELS:
        value = search_group(labeled(label) + r"([一-鿿][^\s]*)", text)
        if value:
            return value
    return ""


def _invoice_type(text: str) -> str:
    flat = compact(text)
    return "电子发票（航空运输电子客票行程单）" if "电子发票" in flat else "航空运输电子客票行程单"


class AirItineraryParser:
    name = "air_itinerary"

    def can_parse(self, path: Path, text: str | None) -> bool:
        content = pdf_text_for_detection(path, text)
        if not content:
            return False
        flat = compact(content)
        return "行程单" in flat and ("航空" in flat or "航班" in flat)

    def parse(self, path: Path, text: str | None) -> ParsedInvoice:
        raw_text = pdf_text_or_raise(path, text)
        normalized = normalize_text(raw_text)
        flight, flown_on = _flight_and_date(normalized)
        fields = TravelFields(
            invoice_no=find_invoice_no(normalized)
            or search_group(TICKET_NO_RE.pattern, normalized),
            issued_on=find_labeled_date(("填开日期", "开票日期"), normalized),
            total_cents=to_cents(search_group(TOTAL_RE.pattern, normalized)),
            seller_name=_seller(normalized),
            invoice_type=_invoice_type(raw_text),
            date=flown_on,
            origin=search_group(ORIGIN_RE.pattern, normalized, re.MULTILINE) or "",
            destination=search_group(DESTINATION_RE.pattern, normalized, re.MULTILINE) or "",
            passenger=search_group(PASSENGER_RE.pattern, normalized) or "",
            train_or_flight=flight,
        )
        return build_travel_invoice(fields, raw_text, self.name)
