"""本次上传内分组：L1 订单号、L2 文件名键、L3 金额日期商家、L4 境外订单↔银行交易。

另含每组一张发票与 V08（同金额不同订单不串组）。
"""

from datetime import date

from invoice_sorting.importer.grouping import group_items
from invoice_sorting.importer.platforms import platform_tokens, platforms_compatible
from tests.evidence_factory import JUNE_28, item

MARCH_12 = date(2026, 3, 12)
JD_SELLER = "江苏京东海元贸易有限公司"


def ids(groups) -> list[list[int]]:
    return [[entry.attachment_id for entry in group.items] for group in groups]


def test_v01_invoice_and_order_linked_by_order_no():
    groups = group_items(
        [
            item(1, "invoice", order_no="3434253000808809", cny_cents=45900, occurred_on=MARCH_12),
            item(2, "order", order_no="3434 2530 0080 8809", occurred_on=date(2026, 3, 1)),
        ]
    )

    assert ids(groups) == [[1, 2]]
    assert groups[0].link_reasons == ("订单号一致",)


def test_file_key_links_and_empty_or_short_key_does_not():
    groups = group_items(
        [
            item(1, "invoice", file_key="打车20260901"),
            item(2, "itinerary", file_key="打车20260901"),
            item(3, "order", file_key=""),
            item(4, "payment", file_key=""),
            item(5, "order", file_key="短键"),
            item(6, "payment", file_key="短键"),
        ]
    )

    assert ids(groups) == [[1, 2], [3], [4], [5], [6]]
    assert groups[0].link_reasons == ("文件名一致",)


def test_amount_date_merchant_links_different_kinds():
    groups = group_items(
        [
            item(1, "invoice", cny_cents=45900, occurred_on=MARCH_12, merchant=JD_SELLER),
            item(2, "payment", cny_cents=45900, occurred_on=date(2026, 3, 14)),
            item(3, "order", cny_cents=45900, occurred_on=date(2026, 3, 11), merchant="京东"),
            item(4, "order", cny_cents=45900, occurred_on=date(2026, 3, 18), merchant="京东"),
        ]
    )

    assert ids(groups) == [[1, 2, 3], [4]]
    assert groups[0].link_reasons == ("金额与日期一致",)


def test_amount_date_requires_merchant_overlap():
    groups = group_items(
        [
            item(1, "invoice", cny_cents=45900, occurred_on=MARCH_12, merchant=JD_SELLER),
            item(2, "order", cny_cents=45900, occurred_on=MARCH_12, merchant="淘宝"),
        ]
    )

    assert ids(groups) == [[1], [2]]


def test_amount_date_requires_close_date_and_different_kind():
    groups = group_items(
        [
            item(1, "payment", cny_cents=100, occurred_on=MARCH_12),
            item(2, "payment", cny_cents=100, occurred_on=MARCH_12),
            item(3, "order", cny_cents=100, occurred_on=date(2026, 3, 20)),
        ]
    )

    assert ids(groups) == [[1], [2], [3]]


def test_at_most_one_invoice_per_group():
    groups = group_items(
        [
            item(1, "invoice", order_no="A1"),
            item(2, "order", order_no="A1"),
            item(3, "invoice", order_no="A1"),
        ]
    )

    assert ids(groups) == [[1, 2], [3]]


def test_v08_same_amount_different_orders_do_not_merge():
    day = MARCH_12
    groups = group_items(
        [
            item(1, "invoice", order_no="111", cny_cents=9900, occurred_on=day, merchant="京东"),
            item(2, "invoice", order_no="222", cny_cents=9900, occurred_on=day, merchant="京东"),
            item(3, "order", order_no="222", cny_cents=9900, occurred_on=day, merchant="京东"),
            item(4, "order", order_no="111", cny_cents=9900, occurred_on=day, merchant="京东"),
            item(5, "order", order_no="333", cny_cents=9900, occurred_on=day, merchant="京东"),
        ]
    )

    assert ids(groups) == [[1, 4], [2, 3], [5]]


def apple_order(attachment_id: int, **fields):
    defaults = {
        "amount_cents": 2000,
        "currency": "USD",
        "occurred_on": JUNE_28,
        "merchant": "Apple",
        "item_name": "Claude Pro - Monthly",
        "is_foreign": True,
    }
    return item(attachment_id, "order", **{**defaults, **fields})


def bank(attachment_id: int, **fields):
    defaults = {
        "cny_cents": 14426,
        "occurred_on": JUNE_28,
        "merchant": "PP*APPLE.COM/BILL",
        "is_foreign": True,
        "amount_cents": 2000,
        "currency": "USD",
    }
    return item(attachment_id, "payment", **{**defaults, **fields})


def test_v02_foreign_order_links_unique_bank_transaction():
    groups = group_items([apple_order(1), bank(2, occurred_on=date(2026, 6, 30))])

    assert ids(groups) == [[1, 2]]
    assert groups[0].link_reasons == ("境外订单与银行交易日期一致",)


def test_foreign_link_uses_amount_then_card_to_disambiguate():
    groups = group_items(
        [
            apple_order(1, card_last4="1234"),
            bank(2, amount_cents=999),
            bank(3, card_last4="1234"),
            bank(4, card_last4="9999"),
        ]
    )

    assert ids(groups) == [[1, 3], [2], [4]]
    assert groups[0].link_reasons == ("境外订单与银行交易日期一致", "卡号末四位一致")


def test_foreign_link_skips_ambiguous_and_incompatible():
    ambiguous = group_items([apple_order(1), apple_order(2), bank(3)])
    incompatible = group_items([apple_order(1), bank(2, merchant="OPENAI *CHATGPT")])
    too_far = group_items([apple_order(1), bank(2, occurred_on=date(2026, 7, 5))])

    assert ids(ambiguous) == [[1], [2], [3]]
    assert ids(incompatible) == [[1], [2]]
    assert ids(too_far) == [[1], [2]]


def test_platform_compatibility():
    assert platforms_compatible(
        platform_tokens("OpenAI"), platform_tokens("OPENAI *CHATGPT SUBSCR")
    )
    assert platforms_compatible(platform_tokens("Stripe"), platform_tokens("Windsurf"))
    assert platforms_compatible(
        platform_tokens("", "ChatGPT Plus"), platform_tokens("PP*APPLE.COM")
    )
    assert platform_tokens("订单", recognizer="app_store_order") == {"apple"}
    assert not platforms_compatible(platform_tokens("京东"), platform_tokens("淘宝"))


def test_v06_receipt_and_bill_with_different_numbers_share_file_key_group():
    # Windsurf 收据编号与账单编号不同，但属于同一笔境外订阅，按文件名键应合为一组
    key = "软件-windsurf-202603"
    receipt = item(1, kind="order", recognizer="receipt", order_no="2526-2992", file_key=key)
    bill = item(2, kind="order", recognizer="receipt", order_no="VUBUGRLX-0003", file_key=key)
    payment = item(3, kind="payment", recognizer="bank_transaction", file_key=key)

    groups = group_items([receipt, bill, payment])

    assert ids(groups) == [[1, 2, 3]]
