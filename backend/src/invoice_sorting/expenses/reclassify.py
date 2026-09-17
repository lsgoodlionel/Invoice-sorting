"""按最新分类规则检查已有记录：列出分类与建议不一致的记录，管理员确认后批量改正。

仅在依据可靠（商品记忆、文件名分类词、发票税收分类）或当前未分类/为“其他”时给出建议，
避免用关键词猜测覆盖用户有意选择的分类。改正时不写入分类记忆。
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.common.constants import AttachmentKind, ExpenseStatus
from invoice_sorting.common.errors import NotFoundError
from invoice_sorting.config import Settings
from invoice_sorting.db.models import Category, Expense
from invoice_sorting.expenses.service import refresh_expense
from invoice_sorting.importer.classify import OTHER_CATEGORY_NAME, explain_category
from invoice_sorting.importer.group_summary import category_from_filenames
from invoice_sorting.importer.items import item_from_attachment

STRONG_BASIS_PREFIXES = ("商品记忆", "文件名分类词", "发票税收分类")
SENT_STATUSES = frozenset({ExpenseStatus.SENT, ExpenseStatus.REIMBURSED})


@dataclass(frozen=True)
class ReclassifySuggestion:
    expense: Expense
    suggested_category: Category
    basis: str


def _invoice_texts(expense: Expense) -> tuple[str, str, str]:
    for attachment in expense.attachments:
        invoice = attachment.invoice_data
        if attachment.kind == AttachmentKind.INVOICE and invoice is not None:
            return (
                invoice.seller_name or expense.merchant,
                invoice.item_summary,
                invoice.tax_category,
            )
    return expense.merchant, expense.summary, ""


def _suggest(session: Session, expense: Expense) -> ReclassifySuggestion | None:
    items = tuple(item_from_attachment(attachment) for attachment in expense.attachments)
    seller, item_summary, tax_category = _invoice_texts(expense)
    suggestion = explain_category(
        session, seller, item_summary, tax_category, category_from_filenames(session, items)
    )
    if suggestion.category_id is None or suggestion.category_id == expense.category_id:
        return None
    current_name = expense.category.name if expense.category else ""
    is_strong = suggestion.basis.startswith(STRONG_BASIS_PREFIXES)
    if not is_strong and current_name not in ("", OTHER_CATEGORY_NAME):
        return None
    category = session.get(Category, suggestion.category_id)
    if category is None or category.name == OTHER_CATEGORY_NAME:
        return None
    return ReclassifySuggestion(expense, category, suggestion.basis)


def preview_reclassify(session: Session, include_sent: bool = False) -> list[ReclassifySuggestion]:
    query = select(Expense).where(Expense.deleted.is_(False), Expense.status != ExpenseStatus.VOID)
    if not include_sent:
        query = query.where(Expense.status.not_in([str(status) for status in SENT_STATUSES]))
    expenses = session.scalars(query.order_by(Expense.spent_on.desc(), Expense.id.desc()))
    suggestions = (_suggest(session, expense) for expense in expenses)
    return [suggestion for suggestion in suggestions if suggestion is not None]


def apply_reclassify(session: Session, settings: Settings, changes: list[tuple[int, int]]) -> int:
    """逐条改正分类并重算凭证清单；不写入分类记忆。"""
    updated = 0
    for expense_id, category_id in changes:
        expense = session.get(Expense, expense_id)
        if expense is None or expense.deleted:
            raise NotFoundError(f"记录 #{expense_id}")
        if session.get(Category, category_id) is None:
            raise NotFoundError("分类")
        if expense.category_id != category_id:
            expense.category_id = category_id
            session.flush()
            refresh_expense(session, settings, expense, note="按最新规则重新分类")
            updated += 1
    return updated
