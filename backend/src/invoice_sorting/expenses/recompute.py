"""设置变化后批量重算记录清单与状态。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.common.constants import ExpenseStatus
from invoice_sorting.config import Settings
from invoice_sorting.db.models import Expense
from invoice_sorting.expenses.service import refresh_expense

OPEN_STATUSES = (ExpenseStatus.SPENT, ExpenseStatus.INVOICED, ExpenseStatus.COMPLETE)
RECOMPUTE_NOTE = "地区设置变更"


def refresh_open_expenses(session: Session, settings: Settings) -> int:
    """对未删除、状态为已支出/已开票/材料齐全的记录重算清单；返回重算条数。"""
    query = select(Expense).where(
        Expense.deleted.is_(False), Expense.status.in_([str(s) for s in OPEN_STATUSES])
    )
    expenses = list(session.scalars(query.order_by(Expense.id)))
    for expense in expenses:
        refresh_expense(session, settings, expense, note=RECOMPUTE_NOTE)
    return len(expenses)
