"""交通凭证（车票/机票/汽车票/船票订单）识别器单测，输入为虚构构造文本或生成图片。"""

from datetime import date
from pathlib import Path

import pytest

from invoice_sorting.evidence import ocr_available, recognize_evidence
from invoice_sorting.evidence.lines import doc_from_rows, lines_from_text
from invoice_sorting.evidence.recognizers import transport_booking
from invoice_sorting.evidence.recognizers.travel_text import (
    after,
    find_date,
    labeled_date,
    person_name,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "evidence"

RAIL_ROWS = [
    ["订单详情"],
    ["订单号E123456789"],
    ["发车时间 2026-09-10 08:00"],
    ["上海虹桥站 G7 南京南站"],
    ["乘车人 张示例 二等座"],
    ["05车12A号"],
    ["票价¥139.50"],
    ["已支付"],
    ["中国铁路12306"],
]


def test_rail_order_fields() -> None:
    result = transport_booking.recognize(doc_from_rows(RAIL_ROWS))
    assert result is not None
    assert (result.doc_type, result.recognizer) == ("itinerary", "transport_booking")
    assert (result.amount_cents, result.currency) == (13950, "CNY")
    assert result.order_no == "E123456789"
    assert result.occurred_on == date(2026, 9, 10)
    assert result.merchant == "铁路12306"
    assert result.item_name == "上海虹桥-南京南 G7"
    assert result.details == {
        "date": "2026-09-10",
        "from": "上海虹桥",
        "to": "南京南",
        "vehicle": "train",
        "number": "G7",
        "passenger": "张示例",
    }
    assert result.confidence >= 0.9


@pytest.mark.skipif(not ocr_available(), reason="未安装 OCR 依赖")
def test_rail_order_screenshot_ocr() -> None:
    result = recognize_evidence(FIXTURES / "rail_order_12306.png", "差旅-火车票.png")
    assert result.recognizer == "transport_booking"
    assert result.details["number"] == "G7"
    assert result.details["to"] == "南京南"


FLIGHT_TEXT = """携程旅行 机票订单
订单号 3000000000001
航班号 MU5101 经济舱
出发 上海虹桥T2 → 到达 北京首都T3
起飞时间 2026年09月20日 08:00
乘机人 张示例
订单总额 ¥1,080.00"""


def test_flight_order_fields() -> None:
    result = transport_booking.recognize(lines_from_text(FLIGHT_TEXT))
    assert result is not None
    assert result.merchant == "携程"
    assert result.amount_cents == 108000
    assert result.details == {
        "date": "2026-09-20",
        "from": "上海虹桥",
        "to": "北京首都",
        "vehicle": "flight",
        "number": "MU5101",
        "passenger": "张示例",
    }


def test_flight_labels_on_separate_lines() -> None:
    rows = [
        ["东方航空", "订单详情"],
        ["出发地", "上海"],
        ["目的地", "成都"],
        ["航班 FM9401", "08月15日 07:30 起飞"],
        ["乘机人", "李示例"],
        ["下单时间 2026-08-01"],
        ["实付金额", "¥980"],
    ]
    result = transport_booking.recognize(doc_from_rows(rows))
    assert result is not None
    assert result.details["vehicle"] == "flight"
    assert (result.details["from"], result.details["to"]) == ("上海", "成都")
    assert result.details["number"] == "FM9401"
    assert result.details["date"] == "2026-08-15"
    assert result.details["passenger"] == "李示例"
    assert result.merchant == "东方航空"


def test_bus_ticket_fields() -> None:
    text = """巴士管家 汽车票订单
订单编号 B20260915001
上海长途客运总站 → 苏州汽车北站
班次 K1234 发车时间 2026-09-15 09:30
乘车人 赵示例
座位号 12
票价 ¥45.00"""
    result = transport_booking.recognize(lines_from_text(text))
    assert result is not None
    assert result.details["vehicle"] == "bus"
    assert result.details["from"] == "上海长途客运总站"
    assert result.details["to"] == "苏州汽车北站"
    assert result.merchant == "巴士管家"
    assert result.details["number"] == "K1234"
    assert result.amount_cents == 4500


def test_ship_ticket_fields() -> None:
    text = """船票订单
订单号 S88880001
出发港 宁波码头
到达港 舟山码头
船名 示例号 开航时间 2026年10月02日 10:00
乘船人 钱示例
票价 ¥120.00"""
    result = transport_booking.recognize(lines_from_text(text))
    assert result is not None
    assert result.details["vehicle"] == "ship"
    assert (result.details["from"], result.details["to"]) == ("宁波", "舟山")
    assert result.details["number"] == "示例号"
    assert result.details["date"] == "2026-10-02"


def test_amount_fallback_and_no_route() -> None:
    text = "12306 订单\n车次 D3001\n乘车人 孙示例\n2026-05-01 06:00 开\n¥88.00"
    result = transport_booking.recognize(lines_from_text(text))
    assert result is not None
    assert result.amount_cents == 8800
    assert "from" not in result.details
    assert result.item_name == "D3001"


def test_rejects_unrelated_documents() -> None:
    assert transport_booking.recognize(lines_from_text("实付款 ¥10\n订单编号 123")) is None


def test_flight_number_from_text_without_label() -> None:
    text = "\n".join(
        [
            "机票订单 已出票",
            "订单号 9000001",
            "CA1831 北京首都—上海虹桥",
            "2026-06-01 07:00 起飞",
            "乘机人 周示例",
            "¥1,200",
        ]
    )
    result = transport_booking.recognize(lines_from_text(text))
    assert result is not None
    assert result.details["number"] == "CA1831"
    assert (result.details["from"], result.details["to"]) == ("北京首都", "上海虹桥")


def test_travel_text_helpers() -> None:
    assert find_date(None, 2026) is None
    assert find_date("13月40日", 2026) is None
    assert find_date("3月5日", 2026) == date(2026, 3, 5)
    assert after(date(2024, 2, 29), date(2024, 3, 1)) == date(2024, 2, 29)
    assert after(date(2026, 1, 2), date(2026, 12, 30)) == date(2027, 1, 2)
    assert person_name("  ") == ""
    assert labeled_date(lines_from_text("出发 某地"), "出发", 2026) is None
