"""酒店订单识别器单测：构造文本（虚构数据）与生成样本（scripts/make_evidence_fixtures.py）。"""

from datetime import date
from pathlib import Path

import pytest

from invoice_sorting.evidence import ocr_available, recognize_evidence
from invoice_sorting.evidence.lines import doc_from_rows, lines_from_text
from invoice_sorting.evidence.recognizers import hotel_booking
from invoice_sorting.evidence.recognizers.hotel_fields import city_from_address

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "evidence"

CTRIP_TEXT = """订单确认单
请查收您的行程确认单。 房费预付到携程,酒店不提供水单。
订单号 1100000000000009 订单金额: ¥720.00 (个人支付)
苏州 - 苏州示例湖畔酒店
入住日期 2026年8月15日 15:00后 离店日期 2026年8月16日 12:00前
房型 经典大床房 房间数量 1
酒店地址 苏州 江苏苏州工业园区示例街7号 酒店确认号
入住人
李示例
No-show:若订单未入住,将收取首日房费¥750
Copyright © 1999-2026, ctrip.com. all rights reserved"""


def test_ctrip_text_fields() -> None:
    result = hotel_booking.recognize(lines_from_text(CTRIP_TEXT))
    assert result is not None
    assert (result.doc_type, result.recognizer) == ("order", "hotel_booking")
    assert result.order_no == "1100000000000009"
    assert (result.amount_cents, result.currency, result.cny_cents) == (72000, "CNY", 72000)
    assert result.occurred_on == date(2026, 8, 16)
    assert result.merchant == "苏州示例湖畔酒店"
    assert result.item_name == "苏州示例湖畔酒店 08-15至08-16 1晚 1间"
    assert result.details == {
        "city": "苏州",
        "hotel": "苏州示例湖畔酒店",
        "check_in": "2026-08-15",
        "check_out": "2026-08-16",
        "nights": "1",
        "rooms": "1",
        "guest": "李示例",
        "platform": "携程",
    }
    assert result.confidence >= 0.9


def test_ctrip_pdf_fixture() -> None:
    result = recognize_evidence(FIXTURES / "ctrip_hotel.pdf", "BookingConfirmation.pdf")
    assert result.recognizer == "hotel_booking"
    assert result.order_no == "1100000000000001"
    assert result.amount_cents == 131600
    assert result.occurred_on == date(2026, 9, 3)
    assert result.details["city"] == "杭州"
    assert result.details["hotel"] == "杭州西湖示例假日酒店"
    assert (result.details["nights"], result.details["rooms"]) == ("2", "2")
    assert result.details["guest"] == "张示例"
    assert result.item_name == "杭州西湖示例假日酒店 09-01至09-03 2晚 2间"


def test_booking_com_pdf_fixture() -> None:
    result = recognize_evidence(FIXTURES / "booking_hotel.pdf", "confirmation.pdf")
    assert result.recognizer == "hotel_booking"
    assert result.order_no == "4012345678"
    assert (result.amount_cents, result.currency, result.cny_cents) == (36000, "EUR", None)
    assert result.is_foreign is True
    assert result.merchant == "Example Canal Hotel"
    assert result.occurred_on == date(2026, 9, 6)
    assert result.details["check_in"] == "2026-09-04"
    assert result.details["nights"] == "2"
    assert result.details["rooms"] == "1"
    assert result.details["guest"] == "Jane Example"
    assert result.details["platform"] == "Booking.com"


MEITUAN_ROWS = [
    ["订单详情"],
    ["预订成功"],
    ["上海示例假日酒店"],
    ["入住09月10日周四", "离店 09月12日 周六"],
    ["共2晚1间", "大床房"],
    ["入住人王示例"],
    ["地址上海市示例区示例路1号"],
    ["订单号 2600000000000123"],
    ["下单时间 2026-09-01 10:20"],
    ["在线支付", "¥616"],
    ["美团酒店"],
]


def test_meituan_rows_without_year() -> None:
    result = hotel_booking.recognize(doc_from_rows(MEITUAN_ROWS))
    assert result is not None
    assert result.merchant == "上海示例假日酒店"
    assert result.amount_cents == 61600
    assert result.order_no == "2600000000000123"
    assert result.occurred_on == date(2026, 9, 12)
    assert result.details == {
        "city": "上海",
        "hotel": "上海示例假日酒店",
        "check_in": "2026-09-10",
        "check_out": "2026-09-12",
        "nights": "2",
        "rooms": "1",
        "guest": "王示例",
        "platform": "美团",
    }


@pytest.mark.skipif(not ocr_available(), reason="未安装 OCR 依赖")
def test_meituan_screenshot_ocr() -> None:
    result = recognize_evidence(FIXTURES / "meituan_hotel.png", "住宿订单.png")
    assert result.recognizer == "hotel_booking"
    assert result.amount_cents == 61600
    assert result.details["check_out"] == "2026-09-12"
    assert result.details["platform"] == "美团"


@pytest.mark.parametrize(
    ("marker", "platform"),
    [
        ("飞猪旅行", "飞猪"),
        ("www.ly.com", "同程"),
        ("艺龙旅行网", "艺龙"),
        ("去哪儿网", "去哪儿"),
        ("agoda.com", "Agoda"),
        ("Expedia", "Expedia"),
        ("Trip.com", "Trip.com"),
        ("华住会", "华住会"),
        ("锦江酒店", "锦江"),
        ("亚朵", "亚朵"),
        ("", ""),
    ],
)
def test_platform_detection(marker: str, platform: str) -> None:
    text = "\n".join(
        [
            "预订确认",
            "酒店名称: 示例酒店",
            "入住日期 2026-03-01 离店日期 2026-03-02",
            "订单金额 ¥300.00",
            marker or "欢迎入住",
        ]
    )
    result = hotel_booking.recognize(lines_from_text(text))
    assert result is not None
    assert result.details.get("platform", "") == platform
    assert result.merchant == "示例酒店"


def test_english_labels_and_year_rollover() -> None:
    text = "\n".join(
        [
            "Reservation confirmation - Agoda",
            "Hotel name: Example Resort Bali",
            "Booking ID: 998877665",
            "Check-in: Dec 30, 2026",
            "Check-out: Jan 2, 2027",
            "Number of rooms: 2",
            "Lead guest: John Example",
            "Total amount US$420.50",
        ]
    )
    result = hotel_booking.recognize(lines_from_text(text))
    assert result is not None
    assert result.order_no == "998877665"
    assert (result.amount_cents, result.currency) == (42050, "USD")
    assert result.details["nights"] == "3"
    assert result.details["rooms"] == "2"
    assert result.item_name == "Example Resort Bali 12-30至01-02 3晚 2间"


def test_month_day_rollover_without_year() -> None:
    rows = [
        ["示例客栈"],
        ["入住 12月31日", "离店 01月01日"],
        ["订单号 12345678"],
        ["下单时间 2026-12-20"],
        ["实付 ¥200"],
    ]
    result = hotel_booking.recognize(doc_from_rows(rows))
    assert result is not None
    assert result.details["check_in"] == "2026-12-31"
    assert result.details["check_out"] == "2027-01-01"
    assert result.details["nights"] == "1"


def test_missing_amount_lowers_confidence() -> None:
    text = "订单确认单\n示例酒店\n入住日期 2026-03-01\n离店日期 2026-03-02\n入住人 某人"
    result = hotel_booking.recognize(lines_from_text(text))
    assert result is not None
    assert result.amount_cents is None
    assert result.confidence < 1.0


def test_rejects_unrelated_documents() -> None:
    assert hotel_booking.recognize(lines_from_text("实付款 ¥10\n订单编号 123456789")) is None
    assert hotel_booking.recognize(lines_from_text("")) is None


@pytest.mark.parametrize(
    ("address", "city"),
    [
        ("江苏省苏州市工业园区示例街1号", "苏州"),
        ("浙江杭州西湖区示例路1号", "杭州"),
        ("北京市东城区示例胡同1号", "北京"),
        ("示例路1号", ""),
    ],
)
def test_city_from_address(address: str, city: str) -> None:
    assert city_from_address(address) == city


def test_nights_from_text_and_city_label() -> None:
    rows = [
        ["预订确认"],
        ["酒店名称", "示例公寓"],
        ["城市", "成都"],
        ["入住日期 2026-04-01", "共3晚"],
        ["订单号 A-778899"],
        ["总价 ¥900"],
    ]
    result = hotel_booking.recognize(doc_from_rows(rows))
    assert result is not None
    assert result.details["city"] == "成都"
    assert result.details["nights"] == "3"
    assert result.occurred_on == date(2026, 4, 1)
    assert result.order_no == "A-778899"
    assert result.item_name == "示例公寓 3晚"
