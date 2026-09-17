"""build_expense_query：筛选条件与日期口径。"""

from datetime import date

import pytest
from PIL import Image
from sqlalchemy import select

from invoice_sorting.attachments.storage import store_file
from invoice_sorting.common.constants import AttachmentKind, DateBasis
from invoice_sorting.db.models import Batch, Category, InvoiceData, Project
from invoice_sorting.expenses.queries import ExpenseFilter, build_expense_query
from invoice_sorting.expenses.service import create_expense, set_status, soft_delete_expense


def ids(session, filters: ExpenseFilter) -> set[int]:
    return {expense.id for expense in session.scalars(build_expense_query(filters))}


@pytest.fixture
def data(session, settings, tmp_path):
    cat = session.scalar(select(Category.id).where(Category.name == "易耗品"))
    project = Project(name="科研A")
    batch = Batch(name="批次", status="sent")
    session.add_all([project, batch])
    session.flush()
    a = create_expense(
        session, settings, spent_on=date(2026, 9, 1), amount_cents=100, merchant="京东",
        summary="鼠标", category_id=cat, project_id=project.id,
    )  # fmt: skip
    b = create_expense(
        session, settings, spent_on=date(2026, 9, 30), amount_cents=200, merchant="腾讯云",
        summary="会议会员",
    )  # fmt: skip
    c = create_expense(
        session, settings, spent_on=date(2026, 10, 1), amount_cents=300, merchant="滴滴出行",
    )  # fmt: skip
    src = tmp_path / "fp.png"
    Image.new("RGB", (5, 5)).save(src)
    invoice = store_file(session, settings, src, "fp.png", AttachmentKind.INVOICE, b)
    invoice.invoice_data = InvoiceData(invoice_no="2431200000009", issued_on=date(2026, 10, 5))
    c.batch_id = batch.id
    c.sent_on = date(2026, 10, 10)
    c.reimbursed_on = date(2026, 11, 2)
    set_status(session, settings, c, None)
    session.flush()
    return {"a": a, "b": b, "c": c, "cat": cat, "project": project, "batch": batch}


def test_default_filter_excludes_deleted(session, settings, data):
    soft_delete_expense(session, settings, data["a"])
    assert ids(session, ExpenseFilter()) == {data["b"].id, data["c"].id}
    assert data["a"].id in ids(session, ExpenseFilter(include_deleted=True))


def test_spent_date_range_is_inclusive(session, data):
    filters = ExpenseFilter(start=date(2026, 9, 1), end=date(2026, 9, 30))
    assert ids(session, filters) == {data["a"].id, data["b"].id}


@pytest.mark.parametrize(
    ("basis", "start", "end", "expected"),
    [
        (DateBasis.INVOICED, date(2026, 10, 1), date(2026, 10, 31), {"b"}),
        (DateBasis.SENT, date(2026, 10, 1), date(2026, 10, 31), {"c"}),
        (DateBasis.RECEIVED, date(2026, 11, 1), date(2026, 12, 31), {"c"}),
        (DateBasis.SPENT, date(2026, 10, 1), date(2026, 12, 31), {"c"}),
    ],
)
def test_date_basis(session, data, basis, start, end, expected):
    filters = ExpenseFilter(start=start, end=end, date_basis=basis)
    assert ids(session, filters) == {data[key].id for key in expected}


def test_filters_by_category_project_status_batch(session, data):
    assert ids(session, ExpenseFilter(category_id=data["cat"])) == {data["a"].id}
    assert ids(session, ExpenseFilter(project_id=data["project"].id)) == {data["a"].id}
    assert ids(session, ExpenseFilter(statuses=["reimbursed"])) == {data["c"].id}
    assert ids(session, ExpenseFilter(statuses=["spent", "void"])) == {data["a"].id, data["b"].id}
    assert ids(session, ExpenseFilter(batch_id=data["batch"].id)) == {data["c"].id}
    assert ids(session, ExpenseFilter(unbatched=True)) == {data["a"].id, data["b"].id}


@pytest.mark.parametrize(
    ("q", "expected"), [("京东", "a"), ("会员", "b"), ("0000009", "b"), ("滴滴", "c")]
)
def test_q_matches_merchant_summary_and_invoice_no(session, data, q, expected):
    assert ids(session, ExpenseFilter(q=q)) == {data[expected].id}


def test_q_escapes_like_wildcards(session, data):
    assert ids(session, ExpenseFilter(q="%")) == set()
