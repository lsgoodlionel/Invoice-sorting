"""凭证识别器单测（钱包账单、行程单、识别器选择），输入为虚构构造文本。"""

from datetime import date

from invoice_sorting.evidence.lines import EvidenceText, doc_from_rows, lines_from_text
from invoice_sorting.evidence.recognizers import best_match, ride, wallet

WECHAT_ROWS = [
    ["示例便利店"],
    ["-35.00"],
    ["当前状态", "支付成功"],
    ["支付时间", "2026年3月5日 12:30:00"],
    ["商品", "饮料"],
    ["商户全称", "上海示例便利店有限公司"],
    ["收单机构", "财付通支付科技有限公司"],
    ["支付方式", "招商银行信用卡(4321)"],
    ["交易单号", "4200000000202603050000000001"],
    ["商户单号", "900000000001"],
]


def test_wechat_bill_fields() -> None:
    result = wallet.recognize(doc_from_rows(WECHAT_ROWS))
    assert result is not None
    assert (result.doc_type, result.recognizer) == ("payment", "wallet_bill")
    assert (result.amount_cents, result.currency, result.cny_cents) == (3500, "CNY", 3500)
    assert result.occurred_on == date(2026, 3, 5)
    assert result.merchant == "上海示例便利店有限公司"
    assert result.item_name == "饮料"
    assert result.order_no == "4200000000202603050000000001"
    assert result.card_last4 == "4321"
    assert result.confidence >= 0.9


def test_alipay_bill_fields() -> None:
    rows = [
        ["账单详情"],
        ["示例商户"],
        ["-1,288.00"],
        ["交易成功"],
        ["支付时间", "2026-06-01 09:00:00"],
        ["付款方式", "余额宝"],
        ["商品说明", "示例商品"],
        ["收款方全称", "示例科技有限公司"],
        ["账单分类", "日用百货"],
        ["创建时间", "2026-06-01 08:59:00"],
        ["订单号", "2026060122001400000000000001"],
        ["商家订单号", "T200000000001"],
    ]
    result = wallet.recognize(doc_from_rows(rows))
    assert result is not None
    assert result.amount_cents == 128800
    assert result.merchant == "示例科技有限公司"
    assert result.order_no == "2026060122001400000000000001"
    assert result.card_last4 == ""


RIDE_TEXT = "\n".join(
    [
        "·申请日期: 2026-06-29 ·行程时间: 2026-06-22 至 2026-06-26",
        "·用车人手机号:13800000000·行程总计:共 2笔行程,总计可开票金额46.80元",
        "可开票金额",
        "序号 订单类型 上车时间 所在城市 起点/终点",
        "1 舒享 2026-06-22 12:50:29 上海市 甲地/乙地 ¥18.01",
        "2 轻享 2026-06-26 12:40:55 上海市 ¥28.79",
    ]
)


def test_ride_itinerary_fields() -> None:
    result = ride.recognize(lines_from_text(RIDE_TEXT))
    assert result is not None
    assert (result.doc_type, result.recognizer) == ("itinerary", "ride_itinerary")
    assert (result.amount_cents, result.cny_cents) == (4680, 4680)
    assert result.occurred_on == date(2026, 6, 26)
    assert result.item_name == "共2笔行程"
    assert result.merchant == ""
    assert result.confidence >= 0.9


def test_didi_itinerary_with_platform_and_total() -> None:
    text = "\n".join(
        [
            "滴滴出行-行程单",
            "申请时间:2026-05-02 行程起止日期:2026-04-01 至 2026-04-30",
            "共3笔行程,合计88.50元",
            "序号 车型 上车时间 城市 起点 终点 里程 金额",
        ]
    )
    result = ride.recognize(lines_from_text(text))
    assert result is not None
    assert result.merchant == "滴滴出行"
    assert result.amount_cents == 8850
    assert result.occurred_on == date(2026, 4, 30)
    assert result.item_name == "共3笔行程"


def test_ride_platform_name_lookup() -> None:
    assert ride.platform_name("打车-【享道出行-46.80元】行程单.pdf") == "享道出行"
    assert ride.platform_name("高德打车行程单") == "高德打车"
    assert ride.platform_name("普通文件") == ""


def test_best_match_picks_highest_confidence() -> None:
    doc = doc_from_rows(WECHAT_ROWS)
    result = best_match(doc)
    assert result is not None
    assert result.recognizer == "wallet_bill"


def test_best_match_returns_none_for_low_confidence() -> None:
    assert best_match(lines_from_text("随便一段文字\n订单 12.00")) is None
    assert best_match(EvidenceText()) is None


def test_best_match_survives_recognizer_error(monkeypatch) -> None:
    from invoice_sorting.evidence import recognizers

    def boom(doc: EvidenceText) -> None:
        raise RuntimeError("bad")

    monkeypatch.setattr(recognizers, "RECOGNIZERS", (boom, wallet.recognize))
    result = best_match(doc_from_rows(WECHAT_ROWS))
    assert result is not None
    assert result.recognizer == "wallet_bill"


def test_wallet_bill_fallbacks_without_labels() -> None:
    rows = [
        ["账单详情"],
        ["示例小店"],
        ["当前状态", "支付成功"],
        ["付款金额", "12.50"],
        ["支付时间", "2026-07-01 08:00:00"],
        ["商户单号", "T20260701-0001"],
        ["支付方式", "零钱"],
    ]
    result = wallet.recognize(doc_from_rows(rows))
    assert result is not None
    assert result.amount_cents == 1250
    assert result.merchant == "示例小店"
    assert result.order_no == "T20260701-0001"
