"""附件业务操作：改类型、改归属、删除，并刷新受影响的支出记录。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.attachments.storage import (
    assign_attachment,
    relocate_attachment,
    trash_attachment,
)
from invoice_sorting.attachments.thumbnails import remove_thumbnail
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.common.errors import NotFoundError
from invoice_sorting.config import Settings
from invoice_sorting.db.models import Attachment, Expense
from invoice_sorting.expenses.amounts import invoice_total, merge_invoice_amounts
from invoice_sorting.expenses.service import get_expense_or_404, refresh_expense


def get_attachment_or_404(session: Session, attachment_id: int) -> Attachment:
    attachment = session.get(Attachment, attachment_id)
    if attachment is None:
        raise NotFoundError("附件")
    return attachment


def list_unassigned(session: Session) -> list[Attachment]:
    query = (
        select(Attachment)
        .where(Attachment.expense_id.is_(None))
        .order_by(Attachment.created_at.desc(), Attachment.id.desc())
    )
    return list(session.scalars(query))


def _refresh_all(session: Session, settings: Settings, expenses: list[Expense | None]) -> None:
    seen: set[int] = set()
    for expense in expenses:
        if expense is None or expense.id in seen or expense.deleted:
            continue
        seen.add(expense.id)
        refresh_expense(session, settings, expense)


def update_attachment(
    session: Session,
    settings: Settings,
    attachment: Attachment,
    *,
    kind: AttachmentKind | None = None,
    change_expense: bool = False,
    expense_id: int | None = None,
) -> Attachment:
    """修改类型和/或归属（change_expense=True 时 expense_id=None 表示移回待归属）。"""
    previous = attachment.expense
    target = previous
    if change_expense:
        target = get_expense_or_404(session, expense_id) if expense_id is not None else None
    if kind is not None:
        attachment.kind = str(kind)
    if change_expense and target is not previous:
        previous_total = invoice_total(session, target) if target is not None else 0
        assign_attachment(session, settings, attachment, target)
        if target is not None:
            merge_invoice_amounts(session, target, previous_total)
    else:
        relocate_attachment(session, settings, attachment)
    _refresh_all(session, settings, [previous, target])
    return attachment


def delete_attachment(session: Session, settings: Settings, attachment: Attachment) -> None:
    expense = attachment.expense
    remove_thumbnail(settings, attachment)
    trash_attachment(session, settings, attachment)
    _refresh_all(session, settings, [expense])
