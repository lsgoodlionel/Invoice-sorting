"""补传附件的自动识别（清单行拖放）：能解析为发票则写发票数据，否则识别凭证并写 EvidenceData。"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.attachments import evidence_records
from invoice_sorting.attachments.storage import absolute_path, relocate_attachment
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.config import Settings
from invoice_sorting.db.models import Attachment, InvoiceData
from invoice_sorting.importer.suggestions import invoice_data_from
from invoice_sorting.parsers import ParsedInvoice, parse_invoice_file

logger = logging.getLogger(__name__)


def _parse(settings: Settings, attachment: Attachment) -> ParsedInvoice | None:
    try:
        return parse_invoice_file(absolute_path(settings, attachment))
    except Exception:
        logger.exception("补传文件解析发票失败：%s", attachment.original_name)
        return None


def _number_taken(session: Session, invoice_no: str | None) -> bool:
    if not invoice_no:
        return False
    query = select(InvoiceData.attachment_id).where(InvoiceData.invoice_no == invoice_no)
    return session.scalar(query) is not None


def recognize_attachment(session: Session, settings: Settings, attachment: Attachment) -> None:
    """按识别结果设置类型并写入识别数据；发票号已存在时不写发票数据，改按凭证识别。"""
    parsed = _parse(settings, attachment)
    if parsed is not None and not _number_taken(session, parsed.invoice_no):
        attachment.kind = str(AttachmentKind.INVOICE)
        invoice = invoice_data_from(parsed)
        invoice.confirmed = attachment.expense_id is not None
        attachment.invoice_data = invoice
    else:
        path = absolute_path(settings, attachment)
        recognized = evidence_records.recognize_file(path, attachment.original_name)
        guessed = AttachmentKind(attachment.kind)
        kind = evidence_records.kind_for_evidence(recognized, attachment.original_name, guessed)
        attachment.kind = str(kind)
        evidence = evidence_records.apply_evidence(attachment, recognized)
        evidence.confirmed = attachment.expense_id is not None
    session.flush()
    relocate_attachment(session, settings, attachment)
