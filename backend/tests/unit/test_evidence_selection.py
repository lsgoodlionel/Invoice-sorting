"""识别器选择对比：京东订单、打车行程单、携程酒店订单、12306 订单各自只命中自己的识别器。"""

import pytest

from invoice_sorting.evidence.lines import EvidenceText, doc_from_rows, lines_from_text
from invoice_sorting.evidence.recognizers import (
    MIN_CONFIDENCE,
    best_match,
    ecommerce,
    hotel_booking,
    ride,
    transport_booking,
)
from tests.unit.test_evidence_hotel import CTRIP_TEXT, MEITUAN_ROWS
from tests.unit.test_evidence_recognizers import JD_ROWS
from tests.unit.test_evidence_recognizers_more import RIDE_TEXT
from tests.unit.test_evidence_transport import FLIGHT_TEXT, RAIL_ROWS

DOCS: dict[str, EvidenceText] = {
    "jd_order": doc_from_rows(JD_ROWS),
    "ride_itinerary": lines_from_text(RIDE_TEXT),
    "hotel_booking": lines_from_text(CTRIP_TEXT),
    "meituan_hotel": doc_from_rows(MEITUAN_ROWS),
    "transport_booking": doc_from_rows(RAIL_ROWS),
    "flight_booking": lines_from_text(FLIGHT_TEXT),
}
EXPECTED = {
    "jd_order": "jd_order",
    "ride_itinerary": "ride_itinerary",
    "hotel_booking": "hotel_booking",
    "meituan_hotel": "hotel_booking",
    "transport_booking": "transport_booking",
    "flight_booking": "transport_booking",
}
CONTENDERS = {
    "jd_order": ecommerce.recognize,
    "ride_itinerary": ride.recognize,
    "hotel_booking": hotel_booking.recognize,
    "transport_booking": transport_booking.recognize,
}


@pytest.mark.parametrize("name", sorted(DOCS))
def test_best_match_picks_own_recognizer(name: str) -> None:
    result = best_match(DOCS[name])
    assert result is not None
    assert result.recognizer == EXPECTED[name]


@pytest.mark.parametrize("name", sorted(DOCS))
def test_other_travel_recognizers_stay_below_threshold(name: str) -> None:
    own = EXPECTED[name]
    for recognizer_name, recognize in CONTENDERS.items():
        if recognizer_name == own:
            continue
        result = recognize(DOCS[name])
        assert result is None or result.confidence < MIN_CONFIDENCE, recognizer_name
