"""差旅票 details：铁路/航空 travel 转写，汽车票/船票发票的出行信息识别。"""

from pathlib import Path

import pytest

from invoice_sorting.parsers import ParsedInvoice, parse_invoice_file
from invoice_sorting.parsers.ground_travel import detect_ground_travel, with_ground_travel
from invoice_sorting.parsers.travel_details import travel_details

INVOICES = Path(__file__).resolve().parents[1] / "fixtures" / "invoices"


def _parsed(parser: str, travel: dict[str, str] | None) -> ParsedInvoice:
    return ParsedInvoice(
        invoice_no="1",
        issued_on=None,
        total_cents=100,
        tax_cents=None,
        amount_cents=None,
        seller_name="",
        seller_tax_id="",
        buyer_name="",
        buyer_tax_id="",
        item_summary="",
        tax_category="",
        invoice_type="",
        parser=parser,
        warnings=(),
        raw_text="",
        travel=travel,
    )


def test_rail_ticket_fixture_details() -> None:
    parsed = parse_invoice_file(INVOICES / "rail_ticket.pdf")
    assert parsed is not None
    assert travel_details(parsed) == {
        "date": "2026-09-12",
        "from": "上海虹桥",
        "to": "南京南",
        "vehicle": "train",
        "number": "G7",
        "passenger": "张示例",
    }


def test_air_itinerary_fixture_details() -> None:
    parsed = parse_invoice_file(INVOICES / "air_itinerary.pdf")
    assert parsed is not None
    details = travel_details(parsed)
    assert (details["vehicle"], details["number"]) == ("flight", "MU5101")
    assert (details["from"], details["to"]) == ("上海虹桥", "北京首都")


def test_details_empty_without_travel_or_vehicle() -> None:
    assert travel_details(_parsed("digital_pdf", None)) == {}
    assert travel_details(_parsed("digital_pdf", {"date": "2026-01-01"})) == {}


def test_details_skip_empty_values() -> None:
    parsed = _parsed("rail_ticket", {"date": "", "from": "上海", "train_or_flight": ""})
    assert travel_details(parsed) == {"from": "上海", "vehicle": "train"}


def test_details_use_explicit_vehicle() -> None:
    travel = {"vehicle": "bus", "from": "上海", "to": "苏州", "train_or_flight": "K1"}
    assert travel_details(_parsed("digital_pdf", travel)) == {
        "from": "上海",
        "to": "苏州",
        "vehicle": "bus",
        "number": "K1",
    }


def test_bus_ticket_invoice_fixture() -> None:
    parsed = parse_invoice_file(INVOICES / "bus_ticket.pdf")
    assert parsed is not None
    assert parsed.parser == "digital_pdf"
    assert travel_details(parsed) == {
        "date": "2026-09-15",
        "from": "上海",
        "to": "苏州",
        "vehicle": "bus",
        "passenger": "张示例",
    }


def test_plain_invoice_has_no_travel() -> None:
    parsed = parse_invoice_file(INVOICES / "digital_same_line.pdf")
    assert parsed is not None
    assert parsed.travel is None
    assert travel_details(parsed) == {}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "公路客运 汽车票\n起点站: 杭州客运中心 终点站: 宁波汽车南站\n乘车日期: 2026-07-01"
            "\n班次: 1024\n乘车人: 李示例",
            {
                "vehicle": "bus",
                "from": "杭州客运中心",
                "to": "宁波汽车南站",
                "date": "2026-07-01",
                "train_or_flight": "1024",
                "passenger": "李示例",
            },
        ),
        (
            "水路客运 船票\n起点: 上海吴淞码头\n终点: 嵊泗\n乘船日期 2026年8月2日",
            {"vehicle": "ship", "from": "上海吴淞码头", "to": "嵊泗", "date": "2026-08-02"},
        ),
        ("*运输服务*客运服务费\n起点: 某地 终点: 某地", None),
        ("*餐饮服务*餐费", None),
    ],
)
def test_detect_ground_travel(text: str, expected: dict[str, str] | None) -> None:
    assert detect_ground_travel(text) == expected


def test_detect_travel_table_with_vehicle_column() -> None:
    text = (
        "特定业务 旅客运输服务\n"
        "出行人 有效身份证件号 出行日期 出发地 到达地 等级 交通工具类型\n"
        "王示例 3101011990****1234 2026-10-01 宁波 舟山 二等舱 船舶\n"
    )
    assert detect_ground_travel(text) == {
        "vehicle": "ship",
        "from": "宁波",
        "to": "舟山",
        "date": "2026-10-01",
        "passenger": "王示例",
    }


def test_with_ground_travel_keeps_existing_travel() -> None:
    parsed = _parsed("rail_ticket", {"from": "上海"})
    assert with_ground_travel(parsed) is parsed
    plain = _parsed("digital_pdf", None)
    assert with_ground_travel(plain) is plain
