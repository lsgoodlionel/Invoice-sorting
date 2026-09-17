"""报销批次：新建、查询、修改、删除。"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from invoice_sorting.common.constants import BatchStatus
from invoice_sorting.common.errors import ConflictError, NotFoundError
from invoice_sorting.config import Settings
from invoice_sorting.db.models import Attachment, Batch, Expense, Project, now
from invoice_sorting.expenses.service import refresh_expense

BATCH_LOAD_OPTIONS = (
    selectinload(Batch.exports),
    selectinload(Batch.expenses).selectinload(Expense.checklist_items),
    selectinload(Batch.expenses).selectinload(Expense.category),
    selectinload(Batch.expenses).selectinload(Expense.project),
    selectinload(Batch.expenses)
    .selectinload(Expense.attachments)
    .selectinload(Attachment.invoice_data),
)


def get_batch_or_404(session: Session, batch_id: int) -> Batch:
    batch = session.get(Batch, batch_id)
    if batch is None:
        raise NotFoundError("批次")
    return batch


def reload_batch(session: Session, batch: Batch) -> Batch:
    """写操作后刷新批次的关联集合，保证序列化结果与数据库一致。"""
    session.flush()
    session.refresh(batch, attribute_names=["expenses", "exports"])
    return batch


def _ensure_project(session: Session, project_id: int | None) -> None:
    if project_id is not None and session.get(Project, project_id) is None:
        raise NotFoundError("经费项目")


def ensure_draft(batch: Batch) -> None:
    if batch.status != BatchStatus.DRAFT:
        raise ConflictError("批次已外发，不能修改")


def list_batches(session: Session, status: BatchStatus | None = None) -> list[Batch]:
    query = select(Batch).options(*BATCH_LOAD_OPTIONS)
    if status is not None:
        query = query.where(Batch.status == str(status))
    query = query.order_by(Batch.created_at.desc(), Batch.id.desc())
    return list(session.scalars(query))


def create_batch(session: Session, *, name: str, project_id: int | None, note: str) -> Batch:
    _ensure_project(session, project_id)
    batch = Batch(
        name=name,
        project_id=project_id,
        note=note,
        status=str(BatchStatus.DRAFT),
        created_at=now(),
    )
    session.add(batch)
    return reload_batch(session, batch)


def update_batch(session: Session, batch: Batch, changes: dict[str, Any]) -> Batch:
    if "project_id" in changes:
        _ensure_project(session, changes["project_id"])
    for key, value in changes.items():
        setattr(batch, key, value)
    return reload_batch(session, batch)


def delete_batch(session: Session, settings: Settings, batch: Batch) -> None:
    """仅待外发批次可删除；记录回到未分批并重新推导状态。导出的文件保留在磁盘上。"""
    if batch.status != BatchStatus.DRAFT:
        raise ConflictError("仅“待外发”的批次可以删除")
    members = list(batch.expenses)
    for expense in members:
        expense.batch = None
    session.flush()
    for expense in members:
        if not expense.deleted:
            refresh_expense(session, settings, expense, note=f"批次『{batch.name}』已删除")
    session.delete(batch)
    session.flush()
