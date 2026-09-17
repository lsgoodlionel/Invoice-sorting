"""匹配“已支出”记录：金额相等、日期 ±7 天、无发票附件、商家相似度优先。"""

from datetime import date
from pathlib import Path

from PIL import Image

from invoice_sorting.attachments.storage import store_file
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.expenses.service import create_expense, set_status, soft_delete_expense
from invoice_sorting.importer.matching import find_spent_match, merchant_similarity

SPENT = date(2026, 9, 15)


def spent(session, settings, merchant="京东", amount=96000, on=SPENT):
    return create_expense(
        session, settings, spent_on=on, amount_cents=amount, merchant=merchant, summary=""
    )


def test_matches_same_amount_within_seven_days(session, settings):
    expense = spent(session, settings)

    assert find_spent_match(session, 96000, date(2026, 9, 22), "京东") is expense
    assert find_spent_match(session, 96000, date(2026, 9, 8), "") is expense


def test_no_match_when_amount_differs_or_date_too_far(session, settings):
    spent(session, settings)

    assert find_spent_match(session, 96001, SPENT, "京东") is None
    assert find_spent_match(session, 96000, date(2026, 9, 23), "京东") is None


def test_no_match_without_amount_or_date(session, settings):
    spent(session, settings)

    assert find_spent_match(session, None, SPENT, "京东") is None
    assert find_spent_match(session, 96000, None, "京东") is None


def test_excludes_deleted_non_spent_and_invoiced(session, settings, tmp_path: Path):
    deleted = spent(session, settings)
    soft_delete_expense(session, settings, deleted)
    voided = spent(session, settings)
    set_status(session, settings, voided, None)
    set_status(session, settings, voided, "void", "个人承担")
    with_invoice = spent(session, settings)
    image = tmp_path / "invoice.png"
    Image.new("RGB", (8, 8), "red").save(image)
    store_file(session, settings, image, "发票.png", AttachmentKind.INVOICE, with_invoice)
    session.flush()

    assert find_spent_match(session, 96000, SPENT, "京东") is None


def test_prefers_similar_merchant_then_closest_date(session, settings):
    spent(session, settings, merchant="淘宝", on=SPENT)
    far_jd = spent(session, settings, merchant="京东", on=date(2026, 9, 10))
    near_jd = spent(session, settings, merchant="京东", on=date(2026, 9, 14))

    match = find_spent_match(session, 96000, SPENT, "北京京东世纪贸易有限公司")
    assert match is near_jd

    match = find_spent_match(session, 96000, date(2026, 9, 9), "京东")
    assert match is far_jd


def test_merchant_similarity_ignores_company_suffix():
    assert merchant_similarity("上海甲有限公司", "北京乙有限公司") == 0
    assert merchant_similarity("京东", "北京京东世纪贸易有限公司") > merchant_similarity(
        "京东", "京西"
    )
    assert merchant_similarity("", "京东") == 0
