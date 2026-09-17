"""开票地区 / 已带明细平台判定，以及清单条件 is_nonlocal、detail_platform。"""

from datetime import date

import pytest
from sqlalchemy import select

from invoice_sorting.checklist.regions import (
    DEFAULT_POLICY,
    RegionPolicy,
    is_detail_platform,
    is_detail_seller,
    is_nonlocal,
    is_nonlocal_region,
    region_name,
)
from invoice_sorting.checklist.service import condition_matches
from invoice_sorting.db.models import Attachment, Category, Expense, InvoiceData
from invoice_sorting.expenses.service import create_expense, refresh_expense
from invoice_sorting.settings.service import update_app_settings
from tests.invoice_factory import store_invoice

NONLOCAL_CONDITION = {"is_nonlocal": True, "detail_platform": False}


def expense_with(*invoices: tuple[str, str], kind: str = "invoice") -> Expense:
    """invoices 为 (开票地区, 销售方) 列表，构造未入库的记录。"""
    attachments = [
        Attachment(kind=kind, invoice_data=InvoiceData(region_name=region, seller_name=seller))
        for region, seller in invoices
    ]
    return Expense(amount_cents=10000, is_online=False, attachments=attachments)


@pytest.mark.parametrize(
    ("region", "local", "expected"),
    [
        ("北京", "上海", True),
        ("上海", "上海", False),
        ("上海市", "上海", False),
        ("上海", "上海市", False),
        ("", "上海", False),
        ("北京", "", False),
        ("  ", "上海", False),
    ],
)
def test_is_nonlocal_region(region, local, expected):
    assert is_nonlocal_region(region, local) is expected


@pytest.mark.parametrize(
    ("seller", "expected"),
    [
        ("北京京东世纪贸易有限公司", True),
        ("上海圆迈贸易有限公司", True),
        ("当当网信息技术（天津）有限公司", True),
        ("北京文具商行有限公司", False),
        ("", False),
        (None, False),
    ],
)
def test_is_detail_seller_matches_platform_keywords(seller, expected):
    assert is_detail_seller(seller, DEFAULT_POLICY.detail_platforms) is expected


def test_empty_keyword_never_matches():
    assert is_detail_seller("任意公司", ["", ""]) is False


def test_expense_level_region_and_platform():
    mixed = expense_with(("上海", "上海某店"), ("北京", "北京京东世纪贸易有限公司"))
    assert is_nonlocal(mixed, "上海") is True
    assert region_name(mixed, "上海") == "北京"
    assert is_detail_platform(mixed, ["京东"]) is True
    local = expense_with(("上海", "上海某店"), ("", "某店"))
    assert is_nonlocal(local, "上海") is False
    assert region_name(local, "上海") == "上海"
    assert region_name(expense_with(), "上海") == ""
    assert is_detail_platform(local, ["京东"]) is False


def test_non_invoice_attachments_are_ignored():
    expense = expense_with(("北京", "北京京东世纪贸易有限公司"), kind="order")
    assert is_nonlocal(expense, "上海") is False
    assert is_detail_platform(expense, ["京东"]) is False


@pytest.mark.parametrize(
    ("invoices", "expected"),
    [
        ([("北京", "北京文具商行有限公司")], True),  # 外地 + 非明细平台 → 需订单
        ([("北京", "北京京东世纪贸易有限公司")], False),  # 外地 + 京东 → 免
        ([("上海", "上海文具店")], False),  # 本地 → 不需要
        ([], False),
    ],
)
def test_condition_nonlocal_without_detail_platform(invoices, expected):
    assert condition_matches(NONLOCAL_CONDITION, expense_with(*invoices)) is expected


def test_condition_combines_with_amount_and_uses_policy():
    expense = expense_with(("北京", "北京文具商行有限公司"))
    assert condition_matches({**NONLOCAL_CONDITION, "amount_gte": 20000}, expense) is False
    beijing_local = RegionPolicy(local_region="北京", detail_platforms=("京东",))
    assert condition_matches(NONLOCAL_CONDITION, expense, beijing_local) is False
    stationery_platform = RegionPolicy(local_region="上海", detail_platforms=("文具商行",))
    assert condition_matches(NONLOCAL_CONDITION, expense, stationery_platform) is False
    assert condition_matches({"is_nonlocal": False}, expense_with(("上海", "店"))) is True


def _order_item(expense: Expense):
    return next((i for i in expense.checklist_items if i.attachment_kind == "order"), None)


def _other_category(session) -> int:
    return session.scalar(select(Category.id).where(Category.name == "其他"))


def test_default_rule_requires_order_for_nonlocal_invoice(session, settings, tmp_path):
    expense = create_expense(
        session,
        settings,
        spent_on=date(2026, 9, 10),
        amount_cents=12800,
        merchant="北京文具商行",
        category_id=_other_category(session),
    )
    assert _order_item(expense) is None
    store_invoice(
        session,
        settings,
        tmp_path,
        expense=expense,
        invoice={"region_name": "北京", "seller_name": "北京文具商行有限公司", "confirmed": True},
    )
    refresh_expense(session, settings, expense)
    item = _order_item(expense)
    assert item is not None and item.level == "required" and "外地发票" in item.hint

    update_app_settings(session, detail_platforms=["文具商行"])
    refresh_expense(session, settings, expense)
    assert _order_item(expense) is None
