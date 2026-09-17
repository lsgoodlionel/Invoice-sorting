"""附件批量操作：批量删除待归属附件、批量归属/移回待归属。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.attachments.storage import (
    assign_attachment,
    relocate_attachment,
    trash_attachment,
)
from invoice_sorting.attachments.thumbnails import remove_thumbnail
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.common.errors import ConflictError, NotFoundError
from invoice_sorting.config import Settings
from invoice_sorting.db.models import Attachment, Expense
from invoice_sorting.expenses.service import (
    get_expense_or_404,
    refresh_expense,
    remember_invoice_category,
)

MAX_LISTED = 5
NOT_UNASSIGNED_MESSAGE = "以下附件已归属记录，不能批量删除（请先移回待归属或在记录中删除）：{names}"
MISSING_MESSAGE = "附件不存在：{ids}"


def load_attachments(session: Session, ids: list[int]) -> list[Attachment]:
    """按请求顺序读取附件（去重）；任一不存在时抛 404。"""
    unique_ids = list(dict.fromkeys(ids))
    rows = session.scalars(select(Attachment).where(Attachment.id.in_(unique_ids)))
    by_id = {attachment.id: attachment for attachment in rows}
    missing = [attachment_id for attachment_id in unique_ids if attachment_id not in by_id]
    if missing:
        error = NotFoundError("附件")
        error.message = MISSING_MESSAGE.format(ids="、".join(f"#{i}" for i in missing))
        raise error
    return [by_id[attachment_id] for attachment_id in unique_ids]


def _describe(attachments: list[Attachment]) -> str:
    names = [f"{item.original_name}（#{item.id}）" for item in attachments[:MAX_LISTED]]
    suffix = f" 等 {len(attachments)} 个" if len(attachments) > MAX_LISTED else ""
    return "、".join(names) + suffix


def refresh_expenses(session: Session, settings: Settings, expenses: list[Expense | None]) -> None:
    """对涉及的记录各刷新一次（跳过空值与已删除记录）。"""
    seen: set[int] = set()
    for expense in expenses:
        if expense is None or expense.deleted or expense.id in seen:
            continue
        seen.add(expense.id)
        refresh_expense(session, settings, expense)


def bulk_delete(session: Session, settings: Settings, ids: list[int]) -> int:
    """批量删除待归属附件：文件移入回收站。含已归属附件时整体拒绝（409）。"""
    attachments = load_attachments(session, ids)
    assigned = [item for item in attachments if item.expense_id is not None]
    if assigned:
        raise ConflictError(NOT_UNASSIGNED_MESSAGE.format(names=_describe(assigned)))
    for attachment in attachments:
        remove_thumbnail(settings, attachment)
        trash_attachment(session, settings, attachment)
    return len(attachments)


def _assign_one(
    session: Session,
    settings: Settings,
    attachment: Attachment,
    target: Expense | None,
    kind: AttachmentKind | None,
) -> None:
    if kind is not None:
        attachment.kind = str(kind)
    if attachment.expense is not target:
        assign_attachment(session, settings, attachment, target)
    else:
        relocate_attachment(session, settings, attachment)
    invoice = attachment.invoice_data
    if target is None or invoice is None or attachment.kind != AttachmentKind.INVOICE:
        return
    invoice.confirmed = True
    if target.category_id is not None:
        remember_invoice_category(session, invoice, target.category_id)


def bulk_assign(
    session: Session,
    settings: Settings,
    ids: list[int],
    expense_id: int | None,
    kind: AttachmentKind | None = None,
) -> list[Attachment]:
    """批量归属到记录（expense_id=None 表示移回待归属），可同时设置类型。"""
    attachments = load_attachments(session, ids)
    target = get_expense_or_404(session, expense_id) if expense_id is not None else None
    affected: list[Expense | None] = [item.expense for item in attachments]
    for attachment in attachments:
        _assign_one(session, settings, attachment, target, kind)
    refresh_expenses(session, settings, [*affected, target])
    return attachments
