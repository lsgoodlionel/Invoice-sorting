"""把待归属发票批量生成记录：复用收件箱自动确认规则，逐条处理，单条失败只跳过该条。"""

import uuid

from sqlalchemy.orm import Session

from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.config import Settings
from invoice_sorting.db.models import Attachment, InvoiceData
from invoice_sorting.importer.auto_confirm import AutoConfirmResult, confirm_import_row
from invoice_sorting.importer.matching import find_spent_match
from invoice_sorting.importer.service import ImportRow
from invoice_sorting.importer.suggestions import suggestion_from_invoice

NOT_INVOICE_REASON = "不是发票，请归属到已有记录"
NO_INVOICE_DATA_REASON = "未识别到发票内容，请先重新识别或手工处理"
ASSIGNED_REASON = "已归属到记录 #{expense_id}，无需生成"


def _ineligible_reason(attachment: Attachment) -> str | None:
    """返回不能生成记录的原因；可以生成时返回 None（此时 invoice_data 一定存在）。"""
    if attachment.expense_id is not None:
        return ASSIGNED_REASON.format(expense_id=attachment.expense_id)
    if attachment.kind != AttachmentKind.INVOICE:
        return NOT_INVOICE_REASON
    if attachment.invoice_data is None:
        return NO_INVOICE_DATA_REASON
    return None


def _import_row(session: Session, attachment: Attachment, invoice: InvoiceData) -> ImportRow:
    """每条处理前重新匹配，避免同一“已支出”记录被前一张发票挂接后再次命中。"""
    suggestion = suggestion_from_invoice(session, invoice)
    match = find_spent_match(
        session, suggestion.amount_cents, suggestion.spent_on, suggestion.merchant
    )
    return ImportRow(uuid.uuid4().hex, attachment, suggestion, match, [])


def create_expenses_from_attachments(
    session: Session, settings: Settings, attachments: list[Attachment]
) -> AutoConfirmResult:
    """按输入顺序处理；调用方负责提交事务。"""
    result = AutoConfirmResult()
    for attachment in attachments:
        reason = _ineligible_reason(attachment)
        if reason is not None:
            result.skip(attachment.id, attachment.original_name, reason)
            continue
        session.flush()
        row = _import_row(session, attachment, attachment.invoice_data)
        confirm_import_row(session, settings, row, result)
    return result
