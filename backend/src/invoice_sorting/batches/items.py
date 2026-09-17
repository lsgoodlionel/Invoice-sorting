"""批次记录的加入与移出：校验批次状态、项目一致性与必需缺项。"""

from sqlalchemy.orm import Session

from invoice_sorting.batches.service import ensure_draft, reload_batch
from invoice_sorting.checklist.service import required_missing_count
from invoice_sorting.common.constants import ExpenseStatus
from invoice_sorting.common.errors import AppError, ConflictError
from invoice_sorting.common.money import cents_to_yuan
from invoice_sorting.config import Settings
from invoice_sorting.db.models import Batch, Expense
from invoice_sorting.expenses.service import get_expense_or_404, refresh_expense

ITEM_SEPARATOR = "；"
NO_PROJECT = "无项目"


def _describe(expense: Expense) -> str:
    return f"#{expense.id} {expense.merchant} {cents_to_yuan(expense.amount_cents)}"


def _project_name(expense_or_batch: Expense | Batch) -> str:
    project = expense_or_batch.project
    return f"『{project.name}』" if project else NO_PROJECT


def _load_additions(session: Session, batch: Batch, ids: list[int]) -> list[Expense]:
    additions: list[Expense] = []
    for expense_id in dict.fromkeys(ids):
        expense = get_expense_or_404(session, expense_id)
        if expense.batch_id == batch.id:
            continue
        if expense.status == ExpenseStatus.VOID:
            raise ConflictError(f"记录 {_describe(expense)} 已作废，不能加入批次")
        if expense.batch_id is not None:
            other = expense.batch.name if expense.batch else f"#{expense.batch_id}"
            raise ConflictError(f"记录 {_describe(expense)} 已在批次『{other}』中")
        additions.append(expense)
    return additions


def _check_project(batch: Batch, additions: list[Expense]) -> None:
    mismatched = [expense for expense in additions if expense.project_id != batch.project_id]
    if not mismatched:
        return
    details = ITEM_SEPARATOR.join(
        f"{_describe(expense)} 属于{_project_name(expense)}" for expense in mismatched
    )
    raise ConflictError(
        f"项目不一致：批次项目为{_project_name(batch)}，{details}；如仍要加入请确认"
    )


def _check_missing(additions: list[Expense]) -> None:
    incomplete = [
        (expense, required_missing_count(expense))
        for expense in additions
        if required_missing_count(expense) > 0
    ]
    if not incomplete:
        return
    details = ITEM_SEPARATOR.join(
        f"{_describe(expense)}（缺 {count} 项）" for expense, count in incomplete
    )
    raise ConflictError(f"以下记录仍缺少必需凭证：{details}{ITEM_SEPARATOR}如仍要加入请确认")


def _auto_project(batch: Batch, additions: list[Expense]) -> None:
    """批次无项目且首次加入记录时，若新记录项目相同则沿用该项目。"""
    has_members = any(not expense.deleted for expense in batch.expenses)
    projects = {expense.project_id for expense in additions}
    if batch.project_id is None and not has_members and len(projects) == 1:
        batch.project_id = projects.pop()


def _check_additions(batch: Batch, additions: list[Expense], force: bool) -> None:
    if force or not additions:
        return
    if batch.project_id is not None:
        _check_project(batch, additions)
    _check_missing(additions)


def _load_removals(session: Session, batch: Batch, ids: list[int]) -> list[Expense]:
    removals: list[Expense] = []
    for expense_id in dict.fromkeys(ids):
        expense = get_expense_or_404(session, expense_id)
        if expense.batch_id != batch.id:
            raise AppError(f"记录 {_describe(expense)} 不在该批次中")
        removals.append(expense)
    return removals


def change_items(
    session: Session,
    settings: Settings,
    batch: Batch,
    *,
    add: list[int],
    remove: list[int],
    force: bool = False,
) -> Batch:
    """加入/移出记录。批次非待外发时禁止修改；校验失败时不做任何改动。"""
    if not add and not remove:
        return reload_batch(session, batch)
    ensure_draft(batch)
    removals = _load_removals(session, batch, remove)
    additions = _load_additions(session, batch, add)
    _check_additions(batch, additions, force)
    _auto_project(batch, additions)
    note = f"移出批次『{batch.name}』"
    for expense in removals:
        expense.batch = None
        refresh_expense(session, settings, expense, note=note)
    for expense in additions:
        expense.batch = batch
        refresh_expense(session, settings, expense, note=f"加入批次『{batch.name}』")
    return reload_batch(session, batch)
