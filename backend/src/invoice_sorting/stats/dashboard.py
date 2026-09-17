"""首页提醒：缺项记录、超期未到账批次、久未开票记录、待归属附件数、本月合计。"""

from datetime import date, timedelta
from typing import Any

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from invoice_sorting.batches.serializers import serialize_batch
from invoice_sorting.batches.service import BATCH_LOAD_OPTIONS
from invoice_sorting.common.constants import (
    BatchStatus,
    ChecklistLevel,
    ChecklistState,
    ExpenseStatus,
)
from invoice_sorting.db.models import Attachment, Batch, ChecklistItem, Expense
from invoice_sorting.expenses.listing import SUMMARY_LOAD_OPTIONS
from invoice_sorting.expenses.serializers import serialize_expense_summary
from invoice_sorting.settings.service import get_app_settings, region_policy
from invoice_sorting.stats.service import StatsQuery, compute_totals, load_entries

MISSING_LIMIT = 20
NO_INVOICE_DAYS = 14
MISSING_STATUSES = (ExpenseStatus.SPENT, ExpenseStatus.INVOICED, ExpenseStatus.COMPLETE)
OVERDUE_STATUSES = (BatchStatus.SENT, BatchStatus.PARTIAL)


def month_bounds(today: date) -> tuple[date, date]:
    first = today.replace(day=1)
    next_first = (first + timedelta(days=32)).replace(day=1)
    return first, next_first - timedelta(days=1)


def _missing_expenses(session: Session) -> list[Expense]:
    has_missing = exists(
        select(ChecklistItem.id).where(
            ChecklistItem.expense_id == Expense.id,
            ChecklistItem.level == ChecklistLevel.REQUIRED,
            ChecklistItem.state == ChecklistState.MISSING,
        )
    )
    query = (
        select(Expense)
        .where(
            Expense.deleted.is_(False),
            Expense.status.in_([str(s) for s in MISSING_STATUSES]),
            has_missing,
        )
        .order_by(Expense.spent_on.desc(), Expense.id.desc())
        .limit(MISSING_LIMIT)
        .options(*SUMMARY_LOAD_OPTIONS)
    )
    return list(session.scalars(query))


def _overdue_batches(session: Session, today: date) -> list[Batch]:
    overdue_days = get_app_settings(session)["overdue_days"]
    query = (
        select(Batch)
        .where(
            Batch.status.in_([str(s) for s in OVERDUE_STATUSES]),
            Batch.sent_on < today - timedelta(days=overdue_days),
        )
        .order_by(Batch.sent_on, Batch.id)
        .options(*BATCH_LOAD_OPTIONS)
    )
    return list(session.scalars(query))


def _spent_without_invoice(session: Session, today: date) -> list[Expense]:
    query = (
        select(Expense)
        .where(
            Expense.deleted.is_(False),
            Expense.status == ExpenseStatus.SPENT,
            Expense.spent_on < today - timedelta(days=NO_INVOICE_DAYS),
        )
        .order_by(Expense.spent_on, Expense.id)
        .options(*SUMMARY_LOAD_OPTIONS)
    )
    return list(session.scalars(query))


def _unassigned_count(session: Session) -> int:
    query = select(func.count()).select_from(Attachment).where(Attachment.expense_id.is_(None))
    return int(session.scalar(query) or 0)


def build_dashboard(session: Session, today: date) -> dict[str, Any]:
    start, end = month_bounds(today)
    month_entries = load_entries(session, StatsQuery(start=start, end=end))
    policy = region_policy(session)
    return {
        "missing": [serialize_expense_summary(e, policy) for e in _missing_expenses(session)],
        "overdue": [serialize_batch(batch) for batch in _overdue_batches(session, today)],
        "spent_without_invoice": [
            serialize_expense_summary(e, policy) for e in _spent_without_invoice(session, today)
        ],
        "unassigned_count": _unassigned_count(session),
        "month_totals": compute_totals([entry.expense for entry in month_entries]),
    }
