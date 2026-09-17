"""批次外发、登记到账与撤销（回到待外发）。"""

from datetime import date

from sqlalchemy.orm import Session

from invoice_sorting.batches.serializers import active_expenses
from invoice_sorting.batches.service import reload_batch
from invoice_sorting.common.constants import BatchStatus
from invoice_sorting.common.errors import AppError, ConflictError
from invoice_sorting.config import Settings
from invoice_sorting.db.models import Batch, Expense
from invoice_sorting.expenses.service import refresh_expense

RECEIVABLE_STATUSES = frozenset({BatchStatus.SENT, BatchStatus.PARTIAL})


def _refresh_all(session: Session, settings: Settings, items: list[Expense], note: str) -> None:
    for expense in items:
        refresh_expense(session, settings, expense, note=note, clear_manual=True)


def mark_sent(
    session: Session,
    settings: Settings,
    batch: Batch,
    *,
    sent_on: date,
    sent_via: str = "",
    receiver: str = "",
    external_no: str = "",
) -> Batch:
    """标记已外发：所有记录的 sent_on 取批次外发日期，并自动推进为“已外发”。"""
    if batch.status != BatchStatus.DRAFT:
        raise ConflictError("批次已外发，如需修改请先撤销外发")
    items = active_expenses(batch)
    if not items:
        raise AppError("空批次不能外发")
    batch.status = str(BatchStatus.SENT)
    batch.sent_on = sent_on
    batch.sent_via = sent_via or batch.sent_via
    batch.receiver = receiver or batch.receiver
    batch.external_no = external_no or batch.external_no
    for expense in items:
        expense.sent_on = sent_on
    session.flush()
    _refresh_all(session, settings, items, f"批次『{batch.name}』已外发")
    return reload_batch(session, batch)


def _select_received(batch: Batch, expense_ids: list[int]) -> list[Expense]:
    items = active_expenses(batch)
    if not expense_ids:
        return items
    by_id = {expense.id: expense for expense in items}
    outside = [str(expense_id) for expense_id in expense_ids if expense_id not in by_id]
    if outside:
        raise AppError(f"以下记录不属于该批次：#{'、#'.join(outside)}")
    return [by_id[expense_id] for expense_id in dict.fromkeys(expense_ids)]


def mark_received(
    session: Session,
    settings: Settings,
    batch: Batch,
    *,
    received_on: date,
    expense_ids: list[int],
) -> Batch:
    """登记到账（全部或部分）。全部到账 → received，否则 partial。"""
    if batch.status not in RECEIVABLE_STATUSES:
        message = "批次已全部到账" if batch.status == BatchStatus.RECEIVED else "批次尚未外发"
        raise ConflictError(f"{message}，不能登记到账")
    selected = _select_received(batch, expense_ids)
    for expense in selected:
        expense.reimbursed_on = received_on
        expense.reimbursed_cents = expense.amount_cents
    items = active_expenses(batch)
    batch.received_on = received_on
    batch.received_cents = sum(e.reimbursed_cents for e in items if e.reimbursed_on is not None)
    all_received = all(expense.reimbursed_on is not None for expense in items)
    batch.status = str(BatchStatus.RECEIVED if all_received else BatchStatus.PARTIAL)
    session.flush()
    _refresh_all(session, settings, selected, f"批次『{batch.name}』已到账")
    return reload_batch(session, batch)


def reopen_batch(session: Session, settings: Settings, batch: Batch) -> Batch:
    """撤销外发/到账：批次回到待外发，清空记录的外发与到账信息并重新推导状态。"""
    if batch.status == BatchStatus.DRAFT:
        raise ConflictError("批次尚未外发，无需撤销")
    batch.status = str(BatchStatus.DRAFT)
    batch.sent_on = None
    batch.received_on = None
    batch.received_cents = 0
    items = active_expenses(batch)
    for expense in items:
        expense.sent_on = None
        expense.reimbursed_on = None
        expense.reimbursed_cents = 0
    session.flush()
    _refresh_all(session, settings, items, f"批次『{batch.name}』撤销外发")
    return reload_batch(session, batch)
