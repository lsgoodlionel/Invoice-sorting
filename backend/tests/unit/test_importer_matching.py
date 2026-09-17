"""凭证组与已有记录匹配：M1 订单号、M2 文件名键、M3 评分阈值与领先、候选范围。"""

from datetime import date
from pathlib import Path

from invoice_sorting.batches.lifecycle import mark_sent
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.db.models import Batch, EvidenceData
from invoice_sorting.expenses.service import (
    create_expense,
    refresh_expense,
    set_status,
    soft_delete_expense,
)
from invoice_sorting.importer.matching import find_candidates, merchant_similarity
from invoice_sorting.importer.scoring import MATCH_THRESHOLD
from tests.evidence_factory import item
from tests.invoice_factory import store_invoice

SPENT = date(2026, 9, 15)


def spent(session, settings, merchant="京东", amount=96000, on=SPENT, **fields):
    return create_expense(
        session, settings, spent_on=on, amount_cents=amount, merchant=merchant, **fields
    )


def invoice_item(amount=96000, on=SPENT, merchant="北京京东世纪贸易有限公司", **fields):
    return item(
        1,
        "invoice",
        cny_cents=amount,
        amount_cents=amount,
        occurred_on=on,
        merchant=merchant,
        **fields,
    )


def test_amount_date_and_missing_invoice_is_strong_match(session, settings):
    expense = spent(session, settings, merchant="京东")

    match, candidates = find_candidates(session, [invoice_item(on=date(2026, 9, 18))])

    assert match is not None and match.expense is expense
    assert match.score >= MATCH_THRESHOLD
    assert match.reasons == ("金额相同", "日期相差 3 天", "商家相同", "正好缺少发票")
    assert candidates == []


def test_week_old_without_merchant_is_only_candidate(session, settings):
    expense = spent(session, settings, merchant="某店")

    match, candidates = find_candidates(session, [invoice_item(on=date(2026, 9, 22), merchant="")])

    assert match is None
    assert [c.expense for c in candidates] == [expense]
    assert candidates[0].score == 40 + 15 + 10


def test_existing_same_kind_is_penalized(session, settings, tmp_path: Path):
    expense = spent(session, settings)
    store_invoice(session, settings, tmp_path, expense=expense, invoice={"invoice_no": "X1"})
    refresh_expense(session, settings, expense)

    match, candidates = find_candidates(session, [invoice_item()])

    assert match is None
    assert candidates[0].score == 40 + 30 + 20 - 30
    assert "已有发票" in candidates[0].reasons


def test_two_close_candidates_are_not_auto_matched(session, settings):
    first = spent(session, settings, merchant="京东")
    second = spent(session, settings, merchant="京东", on=date(2026, 9, 16))

    match, candidates = find_candidates(session, [invoice_item()])

    assert match is None
    assert [c.expense for c in candidates] == [first, second]


def test_excludes_deleted_void_and_sent_batch(session, settings, tmp_path: Path):
    soft_delete_expense(session, settings, spent(session, settings))
    voided = spent(session, settings)
    set_status(session, settings, voided, "void", "个人承担")
    in_batch = spent(session, settings)
    batch = Batch(name="九月")
    session.add(batch)
    session.flush()
    in_batch.batch_id = batch.id
    session.flush()
    mark_sent(session, settings, batch, sent_on=date(2026, 9, 20))

    assert find_candidates(session, [invoice_item()]) == (None, [])


def test_order_number_matches_invoice_or_evidence(session, settings, tmp_path: Path):
    by_invoice = spent(session, settings, amount=1)
    store_invoice(
        session,
        settings,
        tmp_path,
        expense=by_invoice,
        invoice={"invoice_no": "A", "order_no": "3434 2530 0080"},
    )
    order = item(9, "order", order_no="34342530-0080")

    match, _ = find_candidates(session, [order])

    assert match.expense is by_invoice and match.reasons == ("订单号一致",)
    assert match.score == 100


def test_order_number_on_evidence_data(session, settings, tmp_path: Path):
    expense = spent(session, settings, amount=1)
    attachment = store_invoice(
        session, settings, tmp_path, kind=AttachmentKind.PAYMENT, expense=expense
    )
    attachment.evidence_data = EvidenceData(doc_type="payment", order_no="tx-99")
    session.flush()

    match, _ = find_candidates(session, [item(5, "invoice", order_no="TX99")])

    assert match.expense is expense


def test_file_key_match_and_ambiguous_strong_matches(session, settings, tmp_path: Path):
    first, second = spent(session, settings, amount=1), spent(session, settings, amount=2)
    for expense in (first, second):
        attachment = store_invoice(session, settings, tmp_path, expense=expense)
        attachment.file_key = "打车20260901"
    session.flush()

    match, candidates = find_candidates(session, [item(5, "itinerary", file_key="打车20260901")])

    assert match is None
    assert [c.expense for c in candidates] == [first, second]
    assert candidates[0].reasons == ("文件名一致",)
    short = item(6, "itinerary", file_key="打车")
    assert find_candidates(session, [short]) == (None, [])


def test_original_currency_amount_scores(session, settings):
    expense = spent(
        session,
        settings,
        merchant="Apple",
        amount=14426,
        on=date(2026, 6, 28),
        currency="USD",
        original_amount_cents=2000,
        invoice_exempt=True,
    )
    order = item(
        3,
        "order",
        amount_cents=2000,
        currency="USD",
        occurred_on=date(2026, 6, 27),
        merchant="Apple",
        item_name="Claude Pro",
    )

    match, _ = find_candidates(session, [order])

    assert match.expense is expense
    assert match.reasons[:3] == ("原币金额相同", "日期相差 1 天", "商家相同")


def test_no_items_or_no_signal():
    assert find_candidates(None, []) == (None, [])


def test_nothing_to_score(session, settings):
    spent(session, settings)
    assert find_candidates(session, [item(1, "other")]) == (None, [])


def test_merchant_similarity_ignores_company_suffix():
    assert merchant_similarity("上海甲有限公司", "北京乙有限公司") == 0
    assert merchant_similarity("京东", "北京京东世纪贸易有限公司") > merchant_similarity(
        "京东", "京西"
    )
    assert merchant_similarity("", "京东") == 0
