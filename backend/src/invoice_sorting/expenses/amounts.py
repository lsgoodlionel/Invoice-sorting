"""挂附件到已有记录时的金额并入（差旅住宿凭证设计第 5 节）。

记录金额等于挂之前的发票合计（未手动改过）→ 更新为新的发票合计，时间线记“并入交通票 ¥xx”；
手动改过 → 不改金额，时间线提示“金额未自动调整”。记录此前没有发票时不处理（首张发票不改金额）。
调用方：导入确认 attach、收件箱自动确认、批量归属、附件改归属、记录补传附件。
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.common.money import cents_to_yuan
from invoice_sorting.db.models import Attachment, Expense, InvoiceData, StatusEvent, now
from invoice_sorting.importer.items import item_from_attachment

MERGED_NOTE = "并入{label} ¥{added}，金额更新为 ¥{total}"
NOT_ADJUSTED_NOTE = "并入{label} ¥{added}，金额未自动调整（已手动修改过）"
TRANSPORT_LABEL = "交通票"
INVOICE_LABEL = "发票"


def invoice_total(session: Session, expense: Expense) -> int:
    """记录内全部发票的价税合计之和（分）；未识别金额的发票按 0 计。"""
    session.flush()
    query = (
        select(func.coalesce(func.sum(InvoiceData.total_cents), 0))
        .join(Attachment, Attachment.id == InvoiceData.attachment_id)
        .where(Attachment.expense_id == expense.id, Attachment.kind == str(AttachmentKind.INVOICE))
    )
    return int(session.scalar(query) or 0)


def _label(expense: Expense) -> str:
    invoices = [a for a in expense.attachments if a.kind == AttachmentKind.INVOICE]
    is_transport = any(item_from_attachment(a).is_transport for a in invoices)
    return TRANSPORT_LABEL if is_transport else INVOICE_LABEL


def _note(session: Session, expense: Expense, text: str) -> None:
    status = expense.status
    event = StatusEvent(from_status=status, to_status=status, is_manual=False, note=text, at=now())
    expense.status_events.append(event)
    session.flush()


def merge_invoice_amounts(session: Session, expense: Expense, previous_invoice_total: int) -> bool:
    """挂附件之后调用；返回金额是否被更新。调用方随后负责 refresh_expense。"""
    total = invoice_total(session, expense)
    added = total - previous_invoice_total
    if previous_invoice_total <= 0 or added == 0 or expense.amount_cents == total:
        return False
    session.refresh(expense, attribute_names=["attachments"])
    values = {"label": _label(expense), "added": cents_to_yuan(added)}
    if expense.amount_cents != previous_invoice_total:
        _note(session, expense, NOT_ADJUSTED_NOTE.format(**values))
        return False
    expense.amount_cents = total
    _note(session, expense, MERGED_NOTE.format(total=cents_to_yuan(total), **values))
    return True
