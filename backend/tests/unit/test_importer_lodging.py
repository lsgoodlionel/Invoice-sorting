"""差旅住宿凭证：凭证项派生属性、城市词表、L6/L7 分组与多发票组约束（纯函数）。"""

from datetime import date

import pytest

from invoice_sorting.db.models import InvoiceData
from invoice_sorting.importer.cities import find_city, normalize_city, place_in_city
from invoice_sorting.importer.grouping import group_items, hotel_links
from invoice_sorting.importer.items import Stay, invoice_details, travel_details
from invoice_sorting.importer.lodging import (
    hotel_names_match,
    invoices_compatible,
    merge_stays,
    stay_label,
    transport_fits,
    with_fallback_day,
)
from invoice_sorting.importer.lodging_summary import transport_count
from tests.evidence_factory import item
from tests.invoice_factory import parsed_invoice

AUG_15, AUG_16 = date(2026, 8, 15), date(2026, 8, 16)
HOTEL = "苏州园区阳澄湖泰康万豪酒店"
HOTEL_SELLER = "苏州泰康万豪酒店管理有限公司"


def hotel_order(attachment_id=1, **fields):
    details = {
        "city": "苏州",
        "hotel": HOTEL,
        "check_in": "2026-08-15",
        "check_out": "2026-08-16",
        "nights": "1",
        **fields.pop("details", {}),
    }
    base = {"cny_cents": 50000, "amount_cents": 50000, "occurred_on": AUG_16, "merchant": HOTEL}
    return item(
        attachment_id,
        "order",
        recognizer="hotel_booking",
        doc_type="order",
        order_no="1132548283006095",
        details=details,
        **{**base, **fields},
    )


def hotel_invoice(attachment_id=2, **fields):
    base = {
        "cny_cents": 50000,
        "occurred_on": AUG_16,
        "merchant": HOTEL_SELLER,
        "item_name": "住宿费",
        "tax_category": "住宿服务",
    }
    return item(attachment_id, "invoice", **{**base, **fields})


def train(attachment_id, day="2026-08-15", origin="上海虹桥", to="苏州园区", **fields):
    details = {"date": day, "from": origin, "to": to, "vehicle": "train", "number": "G7001"}
    details.update(fields.pop("details", {}))
    base = {"cny_cents": 10000, "occurred_on": date(2026, 8, 20), "details": details}
    return item(attachment_id, fields.pop("kind", "invoice"), **{**base, **fields})


def ids(groups) -> list[list[int]]:
    return [[entry.attachment_id for entry in group.items] for group in groups]


def test_derived_flags_for_lodging_transport_and_order():
    assert hotel_invoice().is_lodging_invoice and not hotel_invoice().is_transport
    assert hotel_order().is_hotel_order and not hotel_order().is_lodging_invoice
    assert item(3, "order", details={"check_in": "2026-08-15"}).is_hotel_order
    assert train(4).is_transport and not train(4).is_lodging_invoice
    assert item(5, "invoice", tax_category="旅客运输服务").is_transport
    assert item(9, "transport").is_transport
    route = {"date": "2026-08-15", "from": "苏州", "to": "上海"}
    assert item(6, "itinerary", doc_type="itinerary", details=route).is_transport
    assert not item(7, "itinerary", doc_type="itinerary", details={"date": "x"}).is_transport
    assert not item(8, "invoice", details={"check_in": "2026-08-15"}).is_hotel_order


def test_stay_from_order_and_from_invoice_seller_city():
    assert hotel_order().stay == Stay(AUG_15, AUG_16, "苏州")
    assert hotel_invoice().stay == Stay(AUG_16, AUG_16, "苏州")
    no_city = hotel_order(details={"city": "", "hotel": "", "check_out": ""}, merchant="全季酒店")
    assert no_city.stay == Stay(AUG_15, AUG_15, "")
    assert train(4).stay is None
    assert train(4, day="bad").travel_date == date(2026, 8, 20)


def test_travel_details_from_parsed_invoice_and_stored_details():
    travel = {"date": "2026-08-15", "from": "上海虹桥", "to": "苏州园区", "train_or_flight": "G1"}
    parsed = parsed_invoice(parser="rail_ticket", travel=travel)
    assert invoice_details(parsed) == {
        "date": "2026-08-15",
        "from": "上海虹桥",
        "to": "苏州园区",
        "vehicle": "train",
        "number": "G1",
    }
    assert travel_details(None) == {}
    assert travel_details({"number": "MU5101", "vehicle": "flight"}, "air_itinerary") == {
        "vehicle": "flight",
        "number": "MU5101",
    }
    assert invoice_details(InvoiceData(parser="", details=None)) == {}
    stored = InvoiceData(parser="rail_ticket", details={"vehicle": "train", "number": ""})
    assert invoice_details(stored) == {"vehicle": "train"}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (HOTEL_SELLER, "苏州"),
        ("华住酒店管理有限公司上海分公司", "上海"),
        ("无城市酒店", ""),
        ("", ""),
        ("连云港某宾馆", "连云港"),
    ],
)
def test_find_city(text, expected):
    assert find_city(text) == expected


def test_normalize_city_and_place_in_city():
    assert normalize_city("苏州市") == "苏州" and normalize_city("市") == "市"
    assert place_in_city("苏州园区", "苏州市") and place_in_city("广州南", "广州")
    assert not place_in_city("上海虹桥", "苏州") and not place_in_city("苏州", "")


def test_hotel_names_ignore_city_and_generic_words():
    assert hotel_names_match(HOTEL_SELLER, HOTEL)
    assert not hotel_names_match("苏州某某酒店有限公司", "苏州另一家酒店")


def test_v_lodging_invoice_order_and_two_trains_in_one_group():
    groups = group_items(
        [
            hotel_invoice(2),
            hotel_order(1),
            train(3),
            train(4, day="2026-08-16", origin="苏州园区", to="上海虹桥", details={"number": "G2"}),
        ]
    )

    assert ids(groups) == [[2, 1, 3, 4]]
    assert groups[0].link_reasons == ("酒店发票与订单一致", "往返酒店所在地的交通凭证")


def test_transport_other_city_or_out_of_window_not_joined():
    groups = group_items(
        [
            hotel_order(1),
            train(2, origin="北京南", to="上海虹桥"),
            train(3, day="2026-08-18", origin="苏州园区", to="上海虹桥"),
            train(4, day="2026-08-14", details={"number": "G3"}),
        ]
    )

    assert ids(groups) == [[1, 4], [2], [3]]


def test_two_lodging_invoices_never_share_a_group():
    groups = group_items(
        [
            hotel_invoice(1),
            hotel_invoice(2, order_no="X1"),
            hotel_order(3),
        ]
    )

    assert all(sum(entry.is_lodging_invoice for entry in group.items) <= 1 for group in groups)
    assert ids(groups) == [[1, 3], [2]]


def test_invoice_mix_rules():
    trains = [train(3), train(4, details={"number": "G2"})]
    assert invoices_compatible([hotel_order(1), *trains])
    assert invoices_compatible([hotel_invoice(2), *trains])
    assert not invoices_compatible(trains)
    assert not invoices_compatible([hotel_invoice(1), hotel_invoice(2)])
    office = item(5, "invoice", tax_category="纸制品")
    assert not invoices_compatible([hotel_invoice(1), office])


def test_invoice_must_match_amount_name_and_window():
    order = hotel_order(0)
    assert hotel_links([hotel_invoice(1), order]) == [(0, 1, ("酒店发票与订单一致",))]
    assert hotel_links([hotel_invoice(2, cny_cents=49900), order]) == []
    assert hotel_links([hotel_invoice(2, occurred_on=date(2026, 9, 20)), order]) == []
    assert hotel_links([hotel_invoice(2, merchant="苏州某某宾馆有限公司"), order]) == []
    undated = hotel_order(0, details={"check_in": "", "check_out": ""})
    assert hotel_links([hotel_invoice(1), undated]) == []


def test_merge_stays_and_labels():
    stays = merge_stays([hotel_order(1), hotel_order(2, details={"check_out": "2026-08-18"})])
    assert stays == Stay(AUG_15, date(2026, 8, 18), "苏州")
    assert merge_stays([train(3)]) is None
    undated = merge_stays([hotel_order(1, details={"check_in": "", "check_out": ""})])
    assert undated == Stay(None, None, "苏州")
    assert with_fallback_day(undated, AUG_15) == Stay(AUG_15, AUG_15, "苏州")
    assert stay_label(undated) == "往返 苏州 的交通凭证"
    assert stay_label(stays) == "往返 苏州 的交通凭证（入住 08-15、离店 08-18）"
    assert not transport_fits(train(3), undated)
    assert not transport_fits(hotel_invoice(), stays)


def test_transport_count_merges_same_trip():
    screenshot = train(5, kind="transport")
    back = train(6, day="2026-08-16", details={"number": "G2"})
    no_details = item(7, "invoice", tax_category="旅客运输服务")
    assert transport_count([train(3), screenshot, back, no_details, hotel_order()]) == 3
