"""重新识别：发票更新票面字段，非发票凭证重新识别并更新 EvidenceData（均保留 confirmed）。

解析失败保持原样；已归属记录的金额/日期/商家不自动改，商家为空时补上。
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.attachments import evidence_records
from invoice_sorting.attachments.bulk import load_attachments, refresh_expenses
from invoice_sorting.attachments.file_keys import compute_file_key
from invoice_sorting.attachments.storage import absolute_path, relocate_attachment
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.config import Settings
from invoice_sorting.db.models import Attachment, Expense, InvoiceData
from invoice_sorting.importer.suggestions import invoice_data_from
from invoice_sorting.parsers import ParsedInvoice, is_probably_invoice, parse_invoice_file

logger = logging.getLogger(__name__)

# 重新识别时覆盖的票面字段（invoice_no 单独处理，confirmed 保留）
FACE_FIELDS = (
    "issued_on",
    "total_cents",
    "tax_cents",
    "seller_name",
    "seller_tax_id",
    "buyer_name",
    "buyer_tax_id",
    "item_summary",
    "invoice_type",
    "tax_category",
    "region_name",
    "order_no",
    "parser",
    "raw_text",
)


def _parse(settings: Settings, attachment: Attachment) -> ParsedInvoice | None:
    path = absolute_path(settings, attachment)
    if not path.is_file():
        return None
    if attachment.kind != AttachmentKind.INVOICE and not is_probably_invoice(path):
        return None
    try:
        return parse_invoice_file(path)
    except Exception:
        logger.exception("重新识别发票失败：%s", attachment.original_name)
        return None


def _number_taken(session: Session, invoice_no: str, attachment_id: int) -> bool:
    query = select(InvoiceData.attachment_id).where(
        InvoiceData.invoice_no == invoice_no, InvoiceData.attachment_id != attachment_id
    )
    return session.scalar(query) is not None


def _resolve_invoice_no(
    session: Session, attachment: Attachment, parsed_no: str | None
) -> str | None:
    """识别到新号码且未被其他发票占用时采用；否则保留原号码。"""
    current = attachment.invoice_data.invoice_no if attachment.invoice_data else None
    if not parsed_no or parsed_no == current:
        return current
    if _number_taken(session, parsed_no, attachment.id):
        logger.info("重新识别的发票号码 %s 已存在，保留原号码", parsed_no)
        return current
    return parsed_no


def _apply(session: Session, attachment: Attachment, parsed: ParsedInvoice) -> None:
    fresh = invoice_data_from(parsed)
    invoice_no = _resolve_invoice_no(session, attachment, parsed.invoice_no)
    invoice = attachment.invoice_data
    if invoice is None:
        invoice = InvoiceData(confirmed=attachment.expense_id is not None)
        attachment.invoice_data = invoice
    for name in FACE_FIELDS:
        setattr(invoice, name, getattr(fresh, name))
    invoice.invoice_no = invoice_no
    attachment.kind = str(AttachmentKind.INVOICE)


def _fill_merchant(expense: Expense | None, seller_name: str) -> None:
    if expense is not None and not (expense.merchant or "").strip() and seller_name:
        expense.merchant = seller_name


def _reparse_evidence(settings: Settings, attachment: Attachment) -> str:
    """重新识别非发票凭证；待归属或类型为“其他”的附件按识别结果改类型。返回识别到的商家。"""
    name = attachment.original_name
    recognized = evidence_records.recognize_file(absolute_path(settings, attachment), name)
    current = AttachmentKind(attachment.kind)
    if attachment.expense_id is None or current == AttachmentKind.OTHER:
        attachment.kind = str(evidence_records.kind_for_evidence(recognized, name, current))
    evidence_records.apply_evidence(attachment, recognized)
    return recognized.merchant or ""


def _reparse_one(session: Session, settings: Settings, attachment: Attachment) -> bool:
    """返回是否有更新。有发票数据的发票解析失败时保持原样。"""
    if not absolute_path(settings, attachment).is_file():
        return False
    attachment.file_key = compute_file_key(attachment.original_name)
    parsed = _parse(settings, attachment)
    if parsed is not None:
        _apply(session, attachment, parsed)
        merchant = parsed.seller_name
    elif attachment.kind != AttachmentKind.INVOICE or attachment.invoice_data is None:
        merchant = _reparse_evidence(settings, attachment)
    else:
        return False
    session.flush()
    relocate_attachment(session, settings, attachment)
    _fill_merchant(attachment.expense, merchant)
    return True


def reparse_attachments(session: Session, settings: Settings, ids: list[int]) -> list[Attachment]:
    """逐个重新识别；返回请求中的全部附件（未识别成功的保持原样）。"""
    attachments = load_attachments(session, ids)
    touched: list[Expense | None] = [
        attachment.expense
        for attachment in attachments
        if _reparse_one(session, settings, attachment)
    ]
    refresh_expenses(session, settings, touched)
    return attachments
