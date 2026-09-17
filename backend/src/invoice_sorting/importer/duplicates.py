"""可能重复（设计 5.2）：同一订单号的同类型凭证已在某条记录中 → 提示并默认跳过。"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.attachments.serializers import kind_label
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.db.models import Attachment, EvidenceData, Expense
from invoice_sorting.importer.items import EvidenceItem
from invoice_sorting.importer.matching import normalized_order_column

DUPLICATE_PREFIX = "可能重复："
DUPLICATE_WARNING = DUPLICATE_PREFIX + "该订单的{label}已在记录 #{expense_id}"
DUPLICATE_LABELS: dict[str, str] = {AttachmentKind.ORDER: "订单截图"}


def _existing_expense_id(session: Session, item: EvidenceItem) -> int | None:
    query = (
        select(Attachment.expense_id)
        .join(EvidenceData, EvidenceData.attachment_id == Attachment.id)
        .join(Expense, Expense.id == Attachment.expense_id)
        .where(
            Expense.deleted.is_(False),
            Attachment.kind == item.kind,
            Attachment.id != item.attachment_id,
            normalized_order_column(EvidenceData.order_no) == item.order_key,
        )
        .order_by(Attachment.expense_id)
        .limit(1)
    )
    return session.scalar(query)


def duplicate_warnings(session: Session, items: Sequence[EvidenceItem]) -> list[str]:
    """发票按发票号判重，这里只检查非发票凭证。"""
    warnings: list[str] = []
    for item in items:
        if item.is_invoice or not item.order_key:
            continue
        expense_id = _existing_expense_id(session, item)
        if expense_id is not None:
            label = DUPLICATE_LABELS.get(item.kind, kind_label(item.kind))
            warnings.append(DUPLICATE_WARNING.format(label=label, expense_id=expense_id))
    return list(dict.fromkeys(warnings))


def has_duplicate_warning(warnings: Sequence[str]) -> bool:
    return any(warning.startswith(DUPLICATE_PREFIX) for warning in warnings)
