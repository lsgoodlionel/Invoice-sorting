"""把待归属附件批量生成记录：所选附件先分组，再按自动确认规则逐组处理（单组失败只跳过该组）。"""

from sqlalchemy.orm import Session

from invoice_sorting.config import Settings
from invoice_sorting.db.models import Attachment
from invoice_sorting.importer.auto_confirm import AutoConfirmResult, auto_confirm_entries
from invoice_sorting.importer.items import item_from_attachment

ASSIGNED_REASON = "已归属到记录 #{expense_id}，无需生成"


def create_expenses_from_attachments(
    session: Session, settings: Settings, attachments: list[Attachment]
) -> AutoConfirmResult:
    """已归属的附件直接跳过；其余按输入顺序分组。调用方负责提交事务。"""
    skipped = AutoConfirmResult()
    pending: list[Attachment] = []
    for attachment in attachments:
        if attachment.expense_id is not None:
            reason = ASSIGNED_REASON.format(expense_id=attachment.expense_id)
            skipped.skip(attachment.id, attachment.original_name, reason)
        else:
            pending.append(attachment)
    entries = [(attachment, item_from_attachment(attachment)) for attachment in pending]
    result = auto_confirm_entries(session, settings, entries)
    return AutoConfirmResult(
        created=result.created,
        attached=result.attached,
        skipped=skipped.skipped + result.skipped,
    )
