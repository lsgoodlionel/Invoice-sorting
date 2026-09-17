"""支出记录查询：列表与统计共用同一筛选函数，保证数字一致。"""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import ColumnElement, Select, and_, exists, func, or_, select

from invoice_sorting.common.constants import (
    AttachmentKind,
    ChecklistLevel,
    ChecklistState,
    DateBasis,
)
from invoice_sorting.db.models import Attachment, ChecklistItem, Expense, InvoiceData


@dataclass(frozen=True)
class ExpenseFilter:
    start: date | None = None
    end: date | None = None  # 含当天
    date_basis: DateBasis = DateBasis.SPENT
    category_id: int | None = None
    project_id: int | None = None
    statuses: list[str] = field(default_factory=list)
    q: str | None = None
    batch_id: int | None = None
    unbatched: bool = False
    missing: bool = False  # 仅含必需缺项的记录
    include_deleted: bool = False


def invoice_issued_on_column() -> ColumnElement[date]:
    """该支出所有发票附件中最早的开票日期（相关子查询）。"""
    return (
        select(func.min(InvoiceData.issued_on))
        .join(Attachment, Attachment.id == InvoiceData.attachment_id)
        .where(Attachment.expense_id == Expense.id, Attachment.kind == AttachmentKind.INVOICE)
        .correlate(Expense)
        .scalar_subquery()
    )


def expense_date_column(date_basis: DateBasis) -> ColumnElement[date]:
    """日期口径 → 对应的日期表达式。统计模块按月分组时也应使用它。"""
    basis = DateBasis(date_basis)
    if basis == DateBasis.INVOICED:
        return invoice_issued_on_column()
    if basis == DateBasis.SENT:
        return Expense.sent_on
    if basis == DateBasis.RECEIVED:
        return Expense.reimbursed_on
    return Expense.spent_on


def _text_condition(q: str) -> ColumnElement[bool]:
    invoice_match = exists(
        select(InvoiceData.attachment_id)
        .join(Attachment, Attachment.id == InvoiceData.attachment_id)
        .where(
            Attachment.expense_id == Expense.id,
            InvoiceData.invoice_no.contains(q, autoescape=True),
        )
    )
    return or_(
        Expense.merchant.contains(q, autoescape=True),
        Expense.summary.contains(q, autoescape=True),
        invoice_match,
    )


def _has_required_missing() -> ColumnElement[bool]:
    return exists().where(
        ChecklistItem.expense_id == Expense.id,
        ChecklistItem.level == ChecklistLevel.REQUIRED,
        ChecklistItem.state == ChecklistState.MISSING,
    )


def _conditions(filters: ExpenseFilter) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if not filters.include_deleted:
        conditions.append(Expense.deleted.is_(False))
    if filters.start is not None or filters.end is not None:
        column = expense_date_column(filters.date_basis)
        if filters.start is not None:
            conditions.append(column >= filters.start)
        if filters.end is not None:
            conditions.append(column <= filters.end)
    if filters.category_id is not None:
        conditions.append(Expense.category_id == filters.category_id)
    if filters.project_id is not None:
        conditions.append(Expense.project_id == filters.project_id)
    if filters.statuses:
        conditions.append(Expense.status.in_([str(status) for status in filters.statuses]))
    if filters.q and filters.q.strip():
        conditions.append(_text_condition(filters.q.strip()))
    if filters.batch_id is not None:
        conditions.append(Expense.batch_id == filters.batch_id)
    if filters.unbatched:
        conditions.append(Expense.batch_id.is_(None))
    if filters.missing:
        conditions.append(_has_required_missing())
    return conditions


def build_expense_query(filters: ExpenseFilter) -> Select[tuple[Expense]]:
    """按筛选条件构造查询，默认按支出日期倒序。"""
    return (
        select(Expense)
        .where(and_(True, *_conditions(filters)))
        .order_by(Expense.spent_on.desc(), Expense.id.desc())
    )
