"""凭证识别器单测：以构造的 OCR 行（虚构数据）为输入，不依赖 OCR。"""

from datetime import date

from invoice_sorting.evidence.lines import doc_from_rows, lines_from_text
from invoice_sorting.evidence.recognizers import app_store, bank, ecommerce, receipt

APP_STORE_ROWS = [
    ["网易邮箱大师"],
    ["订单详细信息"],
    ["Demo Pro - Monthly", "US$20.00"],
    ["订阅续期"],
    ["某人的iPhone"],
    ["2026年6月27日上午12:07"],
    ["PayPal", "US$20.00"],
    ["订单日期", "订单号"],
    ["2026年6月28日", "MTEST12345"],
    ["文稿编号"],
    ["100000000001"],
    ["Apple 账户"],
    ["someone@example.com"],
    ["账单寄送地址"],
    ["管理订阅"],
]


def test_app_store_order_fields() -> None:
    result = app_store.recognize(doc_from_rows(APP_STORE_ROWS))
    assert result is not None
    assert result.doc_type == "order"
    assert result.recognizer == "app_store_order"
    assert (result.amount_cents, result.currency, result.cny_cents) == (2000, "USD", None)
    assert result.occurred_on == date(2026, 6, 28)
    assert result.item_name == "Demo Pro - Monthly"
    assert result.merchant == "Apple"
    assert result.order_no == "MTEST12345"
    assert result.is_foreign is True
    assert result.confidence >= 0.9


def test_app_store_japanese_yen_and_english_labels() -> None:
    text = "\n".join(
        [
            "Order Details",
            "Demo Plus JP¥3,000",
            "Order Date: Mar 5, 2026",
            "Order ID: MABCDE1234",
            "Document No. 200000000002",
            "Apple Account",
        ]
    )
    result = app_store.recognize(lines_from_text(text))
    assert result is not None
    assert (result.amount_cents, result.currency) == (300000, "JPY")
    assert result.occurred_on == date(2026, 3, 5)
    assert result.order_no == "MABCDE1234"


def test_app_store_rejects_unrelated_text() -> None:
    assert app_store.recognize(lines_from_text("实付款 合计¥10\n订单编号 123456789")) is None


RECEIPT_ROWS = [
    ["收据", "D Demoapp"],
    ["账单编号TESTINV-0001"],
    ["收据编号 1111-2222"],
    ["付款日期2026年3月5日"],
    ["Demo Labs, Inc.", "收票人"],
    ["100 Example Street", "某人"],
    ["2026年3月5日支付US$15.00"],
    ["描述", "数量", "单价", "金额"],
    ["Demoapp Pro", "US$15.00", "US$15.00"],
    ["2026年3月5日-2026年4月5日"],
    ["小计", "US$15.00"],
    ["合计", "US$15.00"],
    ["支付额", "US$15.00"],
    ["支付记录"],
    ["支付方式", "日期", "支付额", "收据编号"],
    ["Mastercard - 9876", "2026年3月5日", "US$15.00", "1111-"],
]


def test_receipt_chinese_fields() -> None:
    result = receipt.recognize(doc_from_rows(RECEIPT_ROWS))
    assert result is not None
    assert (result.doc_type, result.recognizer) == ("receipt", "receipt")
    assert (result.amount_cents, result.currency, result.cny_cents) == (1500, "USD", None)
    assert result.occurred_on == date(2026, 3, 5)
    assert result.merchant == "Demo Labs, Inc."
    assert result.item_name == "Demoapp Pro"
    assert result.order_no == "1111-2222"
    assert result.card_last4 == "9876"
    assert result.is_foreign is True
    assert result.confidence >= 0.9


def test_bill_uses_invoice_number_and_due_amount() -> None:
    rows = [
        ["账单", "D Demoapp"],
        ["账单编号 TESTINV-0001"],
        ["发出日期 2026年3月5日"],
        ["到期日", "2026年3月5日"],
        ["2026年3月5日应付US$15.00"],
        ["描述", "数量", "单价", "金额"],
        ["Demoapp Pro", "1", "US$15.00", "US$15.00"],
        ["小计", "US$15.00"],
        ["合计", "US$15.00"],
        ["应付金额", "US$15.00"],
        ["收票人"],
    ]
    result = receipt.recognize(doc_from_rows(rows))
    assert result is not None
    assert result.order_no == "TESTINV-0001"
    assert result.amount_cents == 1500
    assert result.occurred_on == date(2026, 3, 5)
    assert result.merchant == "Demoapp"
    assert result.item_name == "Demoapp Pro"


def test_english_stripe_receipt_text_layer() -> None:
    text = "\n".join(
        [
            "Receipt",
            "Invoice number ABCD1234-0002",
            "Receipt number 3333-4444",
            "Date paid March 7, 2026",
            "Example AI LLC",
            "€9.99 paid on March 7, 2026",
            "Description Qty Unit price Amount",
            "Example Plus 1 €9.99 €9.99",
            "Subtotal €9.99",
            "Total €9.99",
            "Amount paid €9.99",
            "Visa •••• 4242",
        ]
    )
    result = receipt.recognize(lines_from_text(text))
    assert result is not None
    assert (result.amount_cents, result.currency) == (999, "EUR")
    assert result.occurred_on == date(2026, 3, 7)
    assert result.order_no == "3333-4444"
    assert result.merchant == "Example AI LLC"
    assert result.item_name == "Example Plus"
    assert result.card_last4 == "4242"


BANK_ROWS = [
    ["明细详情"],
    ["自消费"],
    ["¥123.45"],
    ["PP*DEMO.COM/BILL 4000000000 USA-+123.45"],
    ["CNY"],
    ["交易卡号(末四位)", "1234"],
    ["交易时间", "2026-04-01"],
    ["原始交易金额", "123.45"],
    ["原始交易币种", "CNY"],
    ["境内外交易标识", "境外"],
    ["交易国家或地区", "美国"],
    ["商户类别", "音像制品商店与音像产品下载"],
    ["入账详情"],
    ["04-03", "消费123.45元，计入04月账单"],
]


def test_bank_transaction_fields() -> None:
    result = bank.recognize(doc_from_rows(BANK_ROWS))
    assert result is not None
    assert (result.doc_type, result.recognizer) == ("payment", "bank_transaction")
    assert (result.amount_cents, result.currency, result.cny_cents) == (12345, "CNY", 12345)
    assert result.occurred_on == date(2026, 4, 1)
    assert result.merchant == "PP*DEMO.COM/BILL"
    assert result.card_last4 == "1234"
    assert result.is_foreign is True
    assert result.item_name == ""
    assert result.confidence >= 0.9


def test_bank_transaction_foreign_currency_keeps_original() -> None:
    rows = [
        ["明细详情"],
        ["消费"],
        ["¥70.00"],
        ["DEMOAPP MOUNTAIN VIEW USA-+10.00 USD 汇"],
        ["率:7.0000"],
        ["交易卡号(末四位)", "5678"],
        ["交易时间", "2026-03-06"],
        ["原始交易金额", "10.00"],
        ["原始交易币种", "USD"],
        ["交易国家或地区", "美国"],
        ["入账详情"],
    ]
    result = bank.recognize(doc_from_rows(rows))
    assert result is not None
    assert result.cny_cents == 7000
    assert result.merchant == "DEMOAPP MOUNTAIN VIEW"
    assert result.item_name == "原币 USD 10.00"
    assert result.is_foreign is True


def test_bank_transaction_domestic() -> None:
    rows = [
        ["明细详情"],
        ["¥35.00"],
        ["财付通-示例餐厅"],
        ["交易卡号(末四位)", "5678"],
        ["交易时间", "2026-03-06"],
        ["境内外交易标识", "境内"],
        ["原始交易币种", "CNY"],
        ["入账详情"],
    ]
    result = bank.recognize(doc_from_rows(rows))
    assert result is not None
    assert result.is_foreign is False
    assert result.merchant == "财付通-示例餐厅"
    assert result.amount_cents == 3500


JD_ROWS = [
    ["自营", "示例家具京东自营旗舰店>"],
    ["LOGO", "示例升降桌...", "1到手¥459"],
    ["¥499"],
    ["数量×1,白色"],
    ["无理由退货政策・7天价保"],
    ["送朋友", "退款/售后", "加购物车"],
    ["实付款", "共减¥40 合计¥459>"],
    ["订单编号", "1000000000000001复制"],
    ["支付方式", "微信支付>"],
    ["支付时间", "2026-03-1117:01:53"],
    ["下单时间", "2026-03-10 17:01:44"],
]


def test_jd_order_fields() -> None:
    result = ecommerce.recognize(doc_from_rows(JD_ROWS))
    assert result is not None
    assert (result.doc_type, result.recognizer) == ("order", "jd_order")
    assert (result.amount_cents, result.currency, result.cny_cents) == (45900, "CNY", 45900)
    assert result.occurred_on == date(2026, 3, 11)
    assert result.merchant == "示例家具京东自营旗舰店"
    assert result.item_name == "示例升降桌"
    assert result.order_no == "1000000000000001"
    assert result.is_foreign is False
    assert result.confidence >= 0.9


def test_taobao_order_text_layer_falls_back_to_order_time() -> None:
    text = "\n".join(
        [
            "示例专营店",
            "示例数据线 2米",
            "实付款 ￥ 1,019.50",
            "订单编号: 2000000000000002",
            "创建时间: 2026/3/5 10:00:00",
            "商品总价 ¥1,100",
        ]
    )
    result = ecommerce.recognize(lines_from_text(text))
    assert result is not None
    assert result.amount_cents == 101950
    assert result.occurred_on == date(2026, 3, 5)
    assert result.merchant == "示例专营店"
    assert result.item_name == "示例数据线 2米"
    assert result.order_no == "2000000000000002"
