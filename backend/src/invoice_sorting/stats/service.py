"""统计（蓝图第 9 节）：与清单列表共用 build_expense_query，保证数字一致。金额为整数分。"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Any

from sqlalchemy.orm import Session, selectinload

from invoice_sorting.common.constants import DateBasis, ExpenseStatus
from invoice_sorting.common.errors import AppError
from invoice_sorting.db.models import Expense
from invoice_sorting.expenses.queries import (
    ExpenseFilter,
    build_expense_query,
    expense_date_column,
)

NONE_KEY = "none"
NO_CATEGORY = "未分类"
NO_PROJECT = "无项目"
NO_MERCHANT = "未填商家"
MAX_MONTHS = 240
PENDING_STATUSES = frozenset({ExpenseStatus.SPENT, ExpenseStatus.INVOICED, ExpenseStatus.COMPLETE})
DATE_BASIS_LABELS: dict[DateBasis, str] = {
    DateBasis.SPENT: "支出日期",
    DateBasis.INVOICED: "开票日期",
    DateBasis.SENT: "外发日期",
    DateBasis.RECEIVED: "到账日期",
}


class StatsGroupBy(StrEnum):
    CATEGORY = "category"
    PROJECT = "project"
    MERCHANT = "merchant"
    MONTH = "month"


@dataclass(frozen=True)
class StatsQuery:
    start: date
    end: date
    date_basis: DateBasis = DateBasis.SPENT
    group_by: StatsGroupBy = StatsGroupBy.CATEGORY


@dataclass(frozen=True)
class StatsEntry:
    """一条参与统计的记录及其按口径取得的日期。"""

    expense: Expense
    basis_date: date


def validate_range(query: StatsQuery) -> None:
    if query.start > query.end:
        raise AppError("开始日期不能晚于结束日期")
    if len(month_keys(query.start, query.end)) > MAX_MONTHS:
        raise AppError(f"统计区间不能超过 {MAX_MONTHS // 12} 年")


def month_keys(start: date, end: date) -> list[str]:
    keys: list[str] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        keys.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        if len(keys) > MAX_MONTHS:
            break
    return keys


def load_entries(session: Session, query: StatsQuery) -> list[StatsEntry]:
    """未删除、口径日期在区间内（含边界）的记录；口径日期为空的记录自然被排除。"""
    filters = ExpenseFilter(start=query.start, end=query.end, date_basis=query.date_basis)
    column = expense_date_column(query.date_basis).label("basis_date")
    statement = (
        build_expense_query(filters)
        .add_columns(column)
        .options(selectinload(Expense.category), selectinload(Expense.project))
    )
    return [StatsEntry(expense, basis_date) for expense, basis_date in session.execute(statement)]


def _is_void(expense: Expense) -> bool:
    return expense.status == ExpenseStatus.VOID


def compute_totals(expenses: list[Expense]) -> dict[str, int]:
    def total(predicate: Callable[[Expense], bool], field: str = "amount_cents") -> int:
        return sum(getattr(expense, field) or 0 for expense in expenses if predicate(expense))

    return {
        "spent_cents": total(lambda e: not _is_void(e)),
        "pending_cents": total(lambda e: e.status in PENDING_STATUSES),
        "in_transit_cents": total(lambda e: e.status == ExpenseStatus.SENT),
        "reimbursed_cents": total(
            lambda e: e.status == ExpenseStatus.REIMBURSED, "reimbursed_cents"
        ),
        "void_cents": total(_is_void),
    }


def _group_key(entry: StatsEntry, group_by: StatsGroupBy) -> tuple[str, str]:
    expense = entry.expense
    if group_by == StatsGroupBy.CATEGORY:
        category = expense.category
        return (str(category.id), category.name) if category else (NONE_KEY, NO_CATEGORY)
    if group_by == StatsGroupBy.PROJECT:
        project = expense.project
        return (str(project.id), project.name) if project else (NONE_KEY, NO_PROJECT)
    if group_by == StatsGroupBy.MERCHANT:
        merchant = (expense.merchant or "").strip()
        return (merchant, merchant) if merchant else (NONE_KEY, NO_MERCHANT)
    month = f"{entry.basis_date:%Y-%m}"
    return month, month


def _empty_by_status() -> dict[str, dict[str, int]]:
    return {status.value: {"count": 0, "amount_cents": 0} for status in ExpenseStatus}


def compute_rows(entries: list[StatsEntry], group_by: StatsGroupBy) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for entry in entries:
        key, label = _group_key(entry, group_by)
        row = groups.setdefault(
            key, {"key": key, "label": label, "by_status": _empty_by_status(), "total_cents": 0}
        )
        expense = entry.expense
        bucket = row["by_status"].setdefault(expense.status, {"count": 0, "amount_cents": 0})
        bucket["count"] += 1
        bucket["amount_cents"] += expense.amount_cents
        if not _is_void(expense):
            row["total_cents"] += expense.amount_cents
    rows = list(groups.values())
    if group_by == StatsGroupBy.MONTH:
        return sorted(rows, key=lambda row: row["key"])
    return sorted(rows, key=lambda row: (-row["total_cents"], row["label"]))


def compute_months(entries: list[StatsEntry], start: date, end: date) -> list[dict[str, Any]]:
    amounts = dict.fromkeys(month_keys(start, end), 0)
    for entry in entries:
        key = f"{entry.basis_date:%Y-%m}"
        if key in amounts and not _is_void(entry.expense):
            amounts[key] += entry.expense.amount_cents
    return [{"month": month, "amount_cents": cents} for month, cents in amounts.items()]


def earliest_date(entries: list[StatsEntry]) -> date | None:
    """区间内最早有数据的口径日期；无数据返回 None。"""
    return min((entry.basis_date for entry in entries), default=None)


def trend_start(start: date, data_start: date | None) -> date:
    """趋势起点：数据起始月初与所选起始日期中较晚者；无数据时保持所选起始日期。"""
    if data_start is None:
        return start
    return max(start, data_start.replace(day=1))


def summarize(query: StatsQuery, entries: list[StatsEntry]) -> dict[str, Any]:
    data_start = earliest_date(entries)
    return {
        "start": query.start.isoformat(),
        "end": query.end.isoformat(),
        "date_basis": str(query.date_basis),
        "data_start": data_start.isoformat() if data_start else None,
        "totals": compute_totals([entry.expense for entry in entries]),
        "rows": compute_rows(entries, query.group_by),
        "months": compute_months(entries, trend_start(query.start, data_start), query.end),
    }
