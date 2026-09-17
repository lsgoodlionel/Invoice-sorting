"""挂到已有记录时补全目标记录：缺分类、缺商家、缺原币信息时补上，不覆盖金额与日期。"""

from typing import Any, Protocol

from sqlalchemy.orm import Session

from invoice_sorting.config import Settings
from invoice_sorting.db.models import Expense
from invoice_sorting.expenses.service import update_expense
from invoice_sorting.importer.journal import FsJournal

CNY = "CNY"


class AttachFields(Protocol):
    category_id: int | None
    merchant: str | None
    currency: str | None
    original_amount_cents: int | None


def attach_changes(expense: Expense, group: AttachFields) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    if expense.category_id is None and group.category_id is not None:
        changes["category_id"] = group.category_id
    if not (expense.merchant or "").strip() and (group.merchant or "").strip():
        changes["merchant"] = group.merchant
    currency = group.currency or CNY
    has_original = group.original_amount_cents is not None and currency != CNY
    if expense.original_amount_cents is None and has_original:
        changes["currency"] = currency
        changes["original_amount_cents"] = group.original_amount_cents
    return changes


def fill_attach_target(
    session: Session, settings: Settings, journal: FsJournal, expense: Expense, group: AttachFields
) -> str:
    """应用补全并记录文件夹改名；返回补全后的文件夹路径。"""
    folder_before = expense.folder_path
    changes = attach_changes(expense, group)
    if not changes:
        return folder_before
    update_expense(session, settings, expense, **changes)
    if folder_before and expense.folder_path != folder_before:
        library = settings.library_dir
        journal.moved(library / folder_before, library / expense.folder_path)
    return expense.folder_path
