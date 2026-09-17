"""凭证识别：文件名线索与文件名键的单测。"""

from datetime import date

import pytest

from invoice_sorting.evidence import file_key, filename_hints


@pytest.mark.parametrize(
    ("left", "right", "key"),
    [
        (
            "办公-20260312-升降桌-459-江苏.pdf",
            "办公-20260312-升降桌-交易订单.PNG",
            "办公-20260312-升降桌",
        ),
        (
            "软件-Claude Pro-202606-订单.png",
            "软件-Claude Pro-202606-银行交易.PNG",
            "软件-claudepro-202606",
        ),
        (
            "打车-202606-【享道出行-46.80元-2个行程】打车电子发票.pdf",
            "打车-202606-【享道出行-46.80元-2个行程】打车电子行程单.pdf",
            None,
        ),
        (
            "软件-Windsurf-202603-收据.PNG",
            "软件-Windsurf-202603-账单.PNG",
            "软件-windsurf-202603",
        ),
        (
            "办公-202606229-7号电池40节-29.9-江苏.pdf",
            "办公-202606229-7号电池40节-交易订单.PNG",
            "办公-202606229-7号电池40节",
        ),
    ],
)
def test_file_key_matches_same_expense(left: str, right: str, key: str | None) -> None:
    assert file_key(left) == file_key(right)
    assert file_key(left) != ""
    if key is not None:
        assert file_key(left) == key


def test_file_key_differs_by_month() -> None:
    assert file_key("软件-Claude Pro-202605-订单.png") != file_key(
        "软件-Claude Pro-202606-订单.png"
    )


@pytest.mark.parametrize("name", ["订单.png", "a-b.pdf", "459-发票.pdf", "", "【】.png"])
def test_file_key_too_short_is_empty(name: str) -> None:
    assert file_key(name) == ""


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("办公-20260312-升降桌-459-江苏.pdf", None),
        ("电子发票-京东.pdf", "invoice"),
        ("普通发票.pdf", "invoice"),
        ("办公-升降桌-交易订单.PNG", "order"),
        ("订单详情.png", "order"),
        ("软件-ChatGPT-202603-银行交易.PNG", "payment"),
        ("交易明细.png", "payment"),
        ("微信支付-美团.png", "payment"),
        ("支付宝-账单详情.png", "payment"),
        ("软件-Windsurf-202603-收据.PNG", "order"),
        ("Invoice-VUBUGRLX-0003.pdf", "order"),
        ("Receipt-2526-2992.pdf", "order"),
        ("打车-【享道出行】打车电子行程单.pdf", "itinerary"),
        ("打车-【享道出行】打车电子发票.pdf", "invoice"),
        ("设备-验收单.pdf", "acceptance"),
        ("软件-服务协议.pdf", "contract"),
        ("采购合同.pdf", "contract"),
    ],
)
def test_filename_kind(name: str, kind: str | None) -> None:
    assert filename_hints(name).kind == kind


def test_filename_hints_full() -> None:
    hints = filename_hints("办公-20260312-升降桌-459-江苏.pdf")
    assert hints.category_word == "办公"
    assert hints.amount_cents == 45900
    assert hints.occurred_on == date(2026, 3, 12)
    assert hints.region == "江苏"
    assert hints.file_key == "办公-20260312-升降桌"


def test_filename_hints_category_plus_and_decimal_amount() -> None:
    hints = filename_hints("图书+办公-20260313-钢笔式毛笔字帖+钢笔式毛笔-36.25-安徽.pdf")
    assert hints.category_word == "图书"
    assert hints.amount_cents == 3625
    assert hints.region == "安徽"


def test_filename_hints_amount_with_yuan_and_year_month() -> None:
    hints = filename_hints("打车-202606-【享道出行-46.80元-2个行程】打车电子行程单.pdf")
    assert hints.category_word == "打车"
    assert hints.amount_cents == 4680
    assert hints.occurred_on == date(2026, 6, 1)
    assert hints.kind == "itinerary"


def test_filename_hints_tolerates_nine_digit_date() -> None:
    hints = filename_hints("办公-202606229-7号电池40节-29.9-江苏.pdf")
    assert hints.occurred_on == date(2026, 6, 22)
    assert hints.amount_cents == 2990


def test_filename_hints_ignores_long_numbers() -> None:
    hints = filename_hints("京东-3434253000808809-订单.png")
    assert hints.amount_cents is None
    assert hints.occurred_on is None
    assert hints.region == ""


def test_filename_hints_without_dash_or_region() -> None:
    hints = filename_hints("收据.png")
    assert hints.category_word == ""
    assert hints.kind == "order"
    assert hints.file_key == ""


def test_filename_hints_region_with_suffix() -> None:
    assert filename_hints("办公-20260101-椅子-上海市.pdf").region == "上海"
