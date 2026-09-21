"""合并执行 · 记录与附件：新 id、改写外键、附件按本地规则落盘。

大包分块处理：每 CHUNK_SIZE 条记录 flush 一次并清空两边会话的对象缓存，内存不随包大小增长；
所有块都在同一个数据库事务里，失败时整体回滚（见 merge.py）。
"""

from collections.abc import Iterable
from dataclasses import dataclass
from itertools import batched

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.attachments.file_keys import compute_file_key
from invoice_sorting.attachments.storage import sync_expense_folder
from invoice_sorting.common.constants import (
    AttachmentKind,
    ChecklistLevel,
    ChecklistState,
    ExpenseStatus,
)
from invoice_sorting.config import Settings
from invoice_sorting.db.models import (
    Attachment,
    Category,
    ChecklistItem,
    EvidenceData,
    Expense,
    InvoiceData,
    StatusEvent,
)
from invoice_sorting.migration.merge_apply import IdMaps, choice, copy_columns
from invoice_sorting.migration.merge_files import FileSource, FileTracker, place_file
from invoice_sorting.migration.merge_plan_records import RecordPlan

CHUNK_SIZE = 200

EXPENSE_EXCLUDE = frozenset(
    {"id", "category_id", "project_id", "batch_id", "created_by_id", "folder_path", "deleted"}
)
ATTACHMENT_EXCLUDE = frozenset({"id", "expense_id", "file_path", "uploaded_by_id", "kind"})
DATA_EXCLUDE = frozenset({"attachment_id"})
ITEM_EXCLUDE = frozenset({"id", "expense_id", "level", "state"})
EVENT_EXCLUDE = frozenset({"id", "expense_id", "actor_id"})


@dataclass(frozen=True)
class ApplyContext:
    db: Session
    pkg: Session
    settings: Settings
    files: FileSource
    tracker: FileTracker
    maps: IdMaps


def apply_records(ctx: ApplyContext, plan: RecordPlan) -> None:
    for chunk in batched(plan.expenses, CHUNK_SIZE):
        query = select(Expense).where(Expense.id.in_(chunk)).order_by(Expense.id)
        for row in ctx.pkg.scalars(query):
            _copy_expense(ctx, row, plan.attachments)
        _release(ctx)
    for chunk in batched(plan.unassigned, CHUNK_SIZE):
        query = select(Attachment).where(Attachment.id.in_(chunk)).order_by(Attachment.id)
        for row in ctx.pkg.scalars(query):
            _copy_attachment(ctx, row, None)
        _release(ctx)


def _release(ctx: ApplyContext) -> None:
    """把本块写入推给数据库（仍在同一事务内），再丢掉对象缓存。"""
    ctx.db.flush()
    ctx.db.expunge_all()
    ctx.pkg.expunge_all()


def _copy_expense(ctx: ApplyContext, row: Expense, wanted: frozenset[int]) -> None:
    db, maps = ctx.db, ctx.maps
    category_id = maps.category(row.category_id)
    expense = Expense(
        **copy_columns(row, EXPENSE_EXCLUDE | {"status"}),
        status=choice(row.status, ExpenseStatus, ExpenseStatus.SPENT),
        category=db.get(Category, category_id) if category_id is not None else None,
        project_id=maps.project(row.project_id),
        batch_id=maps.batch(row.batch_id),
        created_by_id=maps.user(row.created_by_id),
        folder_path="",
        deleted=False,
    )
    db.add(expense)
    db.flush()
    sync_expense_folder(db, ctx.settings, expense)
    ctx.tracker.track_dir(ctx.settings.library_dir / expense.folder_path)
    for attachment in row.attachments:
        if attachment.id in wanted:
            _copy_attachment(ctx, attachment, expense)
    _copy_checklist(db, row.checklist_items, expense.id)
    _copy_events(db, row.status_events, expense.id, maps)


def _copy_attachment(ctx: ApplyContext, row: Attachment, expense: Expense | None) -> None:
    staged = ctx.files.stage(row.file_path)  # 先取文件：校验失败时尽早中止
    attachment = Attachment(
        **copy_columns(row, ATTACHMENT_EXCLUDE),
        kind=choice(row.kind, AttachmentKind, AttachmentKind.OTHER),
        expense=expense,
        file_path="",
        uploaded_by_id=ctx.maps.user(row.uploaded_by_id),
    )
    if not attachment.file_key:
        attachment.file_key = compute_file_key(attachment.original_name)
    if row.invoice_data is not None:
        attachment.invoice_data = InvoiceData(**copy_columns(row.invoice_data, DATA_EXCLUDE))
    if row.evidence_data is not None:
        attachment.evidence_data = EvidenceData(**copy_columns(row.evidence_data, DATA_EXCLUDE))
    ctx.db.add(attachment)
    ctx.db.flush()
    place_file(ctx.db, ctx.settings, attachment, staged, ctx.tracker)


def _copy_checklist(db: Session, items: Iterable[ChecklistItem], expense_id: int) -> None:
    for item in items:
        db.add(
            ChecklistItem(
                **copy_columns(item, ITEM_EXCLUDE),
                expense_id=expense_id,
                level=choice(item.level, ChecklistLevel, ChecklistLevel.REQUIRED),
                state=choice(item.state, ChecklistState, ChecklistState.MISSING),
            )
        )


def _copy_events(db: Session, events: Iterable[StatusEvent], expense_id: int, maps: IdMaps) -> None:
    for event in events:
        db.add(
            StatusEvent(
                **copy_columns(event, EVENT_EXCLUDE),
                expense_id=expense_id,
                actor_id=maps.user(event.actor_id),
            )
        )
