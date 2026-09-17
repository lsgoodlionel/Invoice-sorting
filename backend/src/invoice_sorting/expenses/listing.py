"""支出列表：分页、合计与按状态汇总。"""

from dataclasses import replace
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from invoice_sorting.common.constants import ExpenseStatus
from invoice_sorting.common.errors import AppError
from invoice_sorting.db.models import Attachment, Expense
from invoice_sorting.expenses.queries import ExpenseFilter, build_expense_query
from invoice_sorting.expenses.serializers import serialize_expense_summary

SUMMARY_LOAD_OPTIONS = (
    selectinload(Expense.category),
    selectinload(Expense.project),
    selectinload(Expense.batch),
    selectinload(Expense.checklist_items),
    selectinload(Expense.attachments).selectinload(Attachment.invoice_data),
)


def parse_statuses(raw: str | None) -> list[str]:
    values = [part.strip() for part in (raw or "").split(",") if part.strip()]
    valid = {status.value for status in ExpenseStatus}
    invalid = [value for value in values if value not in valid]
    if invalid:
        raise AppError(f"未知状态：{'、'.join(invalid)}", status_code=422)
    return values


def _status_counts(session: Session, filters: ExpenseFilter) -> dict[str, dict[str, int]]:
    subquery = build_expense_query(replace(filters, statuses=[])).order_by(None).subquery()
    rows = session.execute(
        select(
            subquery.c.status, func.count(), func.coalesce(func.sum(subquery.c.amount_cents), 0)
        ).group_by(subquery.c.status)
    )
    counts = {status.value: {"count": 0, "amount_cents": 0} for status in ExpenseStatus}
    for status, count, amount in rows:
        counts[status] = {"count": int(count), "amount_cents": int(amount)}
    return counts


def list_expenses(
    session: Session, filters: ExpenseFilter, page: int, page_size: int
) -> dict[str, Any]:
    query = build_expense_query(filters)
    subquery = query.order_by(None).subquery()
    total, total_cents = session.execute(
        select(func.count(), func.coalesce(func.sum(subquery.c.amount_cents), 0))
    ).one()
    rows = session.scalars(
        query.options(*SUMMARY_LOAD_OPTIONS).offset((page - 1) * page_size).limit(page_size)
    )
    return {
        "items": [serialize_expense_summary(expense) for expense in rows],
        "total": int(total),
        "total_cents": int(total_cents),
        "status_counts": _status_counts(session, filters),
    }
