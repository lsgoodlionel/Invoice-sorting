"""批次与导出记录的接口形状（docs/api-contract.md: Batch / BatchDetail / ExportRecord）。"""

from pathlib import Path
from typing import Any

from invoice_sorting.attachments.serializers import iso_date, iso_datetime
from invoice_sorting.checklist.service import required_missing_count
from invoice_sorting.common.constants import BATCH_STATUS_LABELS, BatchStatus
from invoice_sorting.db.models import Batch, Expense, ExportRecord
from invoice_sorting.expenses.serializers import serialize_expense_summary


def active_expenses(batch: Batch) -> list[Expense]:
    """批次内未删除的记录，按支出日期升序、id 升序（与资料包序号一致）。"""
    items = [expense for expense in batch.expenses if not expense.deleted]
    return sorted(items, key=lambda expense: (expense.spent_on, expense.id))


def batch_status_label(status: str) -> str:
    try:
        return BATCH_STATUS_LABELS[BatchStatus(status)]
    except ValueError:
        return status


def serialize_batch(batch: Batch) -> dict[str, Any]:
    items = active_expenses(batch)
    project = batch.project
    return {
        "id": batch.id,
        "name": batch.name,
        "project_id": batch.project_id,
        "project_name": project.name if project else None,
        "status": batch.status,
        "status_label": batch_status_label(batch.status),
        "sent_on": iso_date(batch.sent_on),
        "sent_via": batch.sent_via or "",
        "receiver": batch.receiver or "",
        "external_no": batch.external_no or "",
        "received_on": iso_date(batch.received_on),
        "received_cents": batch.received_cents or 0,
        "note": batch.note or "",
        "created_at": iso_datetime(batch.created_at),
        "item_count": len(items),
        "total_cents": sum(expense.amount_cents for expense in items),
        "missing_item_count": sum(1 for expense in items if required_missing_count(expense) > 0),
    }


def serialize_export_record(record: ExportRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "layout": record.layout,
        "file_name": Path(record.file_path).name,
        "url": f"/api/exports/{record.id}/file",
        "sha256": record.sha256,
        "item_count": record.item_count,
        "total_cents": record.total_cents,
        "created_at": iso_datetime(record.created_at),
    }


def serialize_batch_detail(batch: Batch) -> dict[str, Any]:
    exports = sorted(batch.exports, key=lambda record: record.id, reverse=True)
    return {
        **serialize_batch(batch),
        "expenses": [serialize_expense_summary(expense) for expense in active_expenses(batch)],
        "exports": [serialize_export_record(record) for record in exports],
    }
