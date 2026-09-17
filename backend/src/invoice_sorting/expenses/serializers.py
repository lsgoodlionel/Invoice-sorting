"""支出记录的接口形状（docs/api-contract.md: ExpenseSummary / ExpenseDetail）。"""

from typing import Any

from sqlalchemy.orm import Session

from invoice_sorting.attachments.serializers import (
    iso_date,
    iso_datetime,
    kind_label,
    serialize_attachment,
)
from invoice_sorting.checklist.service import required_missing_count
from invoice_sorting.common.constants import AttachmentKind, ExpenseStatus
from invoice_sorting.db.models import ChecklistItem, Expense, StatusEvent
from invoice_sorting.settings.service import buyer_identity


def status_label(status: str) -> str:
    try:
        return ExpenseStatus(status).label
    except ValueError:
        return status


def first_invoice_no(expense: Expense) -> str | None:
    invoices = sorted(
        (a for a in expense.attachments if a.kind == AttachmentKind.INVOICE),
        key=lambda attachment: attachment.id,
    )
    for attachment in invoices:
        if attachment.invoice_data is not None and attachment.invoice_data.invoice_no:
            return attachment.invoice_data.invoice_no
    return None


def serialize_expense_summary(expense: Expense) -> dict[str, Any]:
    category, project, batch = expense.category, expense.project, expense.batch
    return {
        "id": expense.id,
        "spent_on": iso_date(expense.spent_on),
        "amount_cents": expense.amount_cents,
        "merchant": expense.merchant,
        "summary": expense.summary,
        "category_id": expense.category_id,
        "category_name": category.name if category else None,
        "category_color": category.color if category else None,
        "project_id": expense.project_id,
        "project_name": project.name if project else None,
        "status": expense.status,
        "status_label": status_label(expense.status),
        "status_manual": bool(expense.status_manual),
        "missing_count": required_missing_count(expense),
        "batch_id": expense.batch_id,
        "batch_name": batch.name if batch else None,
        "attachment_count": len(expense.attachments),
        "invoice_no": first_invoice_no(expense),
    }


def serialize_checklist_item(item: ChecklistItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "attachment_kind": item.attachment_kind,
        "kind_label": kind_label(item.attachment_kind),
        "level": item.level,
        "state": item.state,
        "reason": item.reason or "",
        "hint": item.hint or "",
    }


def serialize_status_event(event: StatusEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "from_status": event.from_status,
        "to_status": event.to_status,
        "is_manual": bool(event.is_manual),
        "note": event.note or "",
        "at": iso_datetime(event.at),
    }


def serialize_expense_detail(session: Session, expense: Expense) -> dict[str, Any]:
    buyer = buyer_identity(session)
    attachments = sorted(expense.attachments, key=lambda attachment: attachment.id)
    checklist = sorted(expense.checklist_items, key=lambda item: item.id)
    timeline = sorted(expense.status_events, key=lambda event: (iso_datetime(event.at), event.id))
    return {
        **serialize_expense_summary(expense),
        "pay_method": expense.pay_method or "",
        "is_online": bool(expense.is_online),
        "note": expense.note or "",
        "void_reason": expense.void_reason or "",
        "sent_on": iso_date(expense.sent_on),
        "reimbursed_on": iso_date(expense.reimbursed_on),
        "reimbursed_cents": expense.reimbursed_cents or 0,
        "folder_path": expense.folder_path or "",
        "route_hint": expense.category.route_hint if expense.category else "",
        "attachments": [serialize_attachment(attachment, buyer) for attachment in attachments],
        "checklist": [serialize_checklist_item(item) for item in checklist],
        "timeline": [serialize_status_event(event) for event in timeline],
        "created_at": iso_datetime(expense.created_at),
        "updated_at": iso_datetime(expense.updated_at),
    }
