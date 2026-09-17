"""导入确认：新建记录 / 挂到已有记录 / 跳过。任一行失败时撤销文件移动并抛出中文错误。"""

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from invoice_sorting.attachments.storage import absolute_path, assign_attachment
from invoice_sorting.common.errors import AppError
from invoice_sorting.config import Settings
from invoice_sorting.db.models import Attachment, Expense
from invoice_sorting.expenses.service import (
    create_expense,
    get_expense_or_404,
    refresh_expense,
    remember_invoice_category,
    update_expense,
)
from invoice_sorting.importer.journal import FsJournal
from invoice_sorting.importer.schemas import ConfirmRow

logger = logging.getLogger(__name__)

IMPORT_NOTE = "导入发票"


@dataclass
class ConfirmResult:
    created: list[int] = field(default_factory=list)
    attached: list[int] = field(default_factory=list)
    skipped: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "created": self.created,
            "attached": list(dict.fromkeys(self.attached)),
            "skipped": self.skipped,
        }


@dataclass
class _Context:
    session: Session
    settings: Settings
    journal: FsJournal = field(default_factory=FsJournal)
    result: ConfirmResult = field(default_factory=ConfirmResult)
    seen: set[str] = field(default_factory=set)


@contextmanager
def _file_errors(name: str) -> Iterator[None]:
    try:
        yield
    except AppError as exc:
        raise AppError(f"文件“{name}”：{exc.message}", exc.status_code) from exc
    except Exception as exc:
        logger.exception("确认导入失败：%s", name)
        raise AppError(f"文件“{name}”：确认导入失败，请重试") from exc


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AppError(message)


def _assign(ctx: _Context, attachment: Attachment, expense: Expense) -> None:
    if attachment.expense_id is not None:
        raise AppError(f"已归属到记录 #{attachment.expense_id}，请刷新后重试")
    before = absolute_path(ctx.settings, attachment)
    assign_attachment(ctx.session, ctx.settings, attachment, expense)
    ctx.journal.moved(before, absolute_path(ctx.settings, attachment))
    if attachment.invoice_data is not None:
        attachment.invoice_data.confirmed = True
        if expense.category_id is not None:
            remember_invoice_category(ctx.session, attachment.invoice_data, expense.category_id)


def _finish(ctx: _Context, expense: Expense, folder_before: str) -> None:
    refresh_expense(ctx.session, ctx.settings, expense, note=IMPORT_NOTE)
    after = expense.folder_path
    if folder_before and after and folder_before != after:
        library = ctx.settings.library_dir
        ctx.journal.moved(library / folder_before, library / after)


def _create(ctx: _Context, attachment: Attachment, row: ConfirmRow) -> None:
    _require(row.spent_on is not None, "请填写支出日期")
    _require(row.amount_cents is not None, "请填写金额")
    _require(bool(row.merchant), "请填写商家")
    expense = create_expense(
        ctx.session,
        ctx.settings,
        spent_on=row.spent_on,
        amount_cents=row.amount_cents,
        merchant=row.merchant,
        summary=row.summary or "",
        category_id=row.category_id,
        project_id=row.project_id,
    )
    folder_before = expense.folder_path
    if folder_before:
        ctx.journal.created_dir(ctx.settings.library_dir / folder_before)
    _assign(ctx, attachment, expense)
    _finish(ctx, expense, folder_before)
    ctx.result.created.append(expense.id)


def _attach(ctx: _Context, attachment: Attachment, row: ConfirmRow) -> None:
    _require(row.expense_id is not None, "挂到已有记录时需要选择记录")
    expense = get_expense_or_404(ctx.session, row.expense_id)
    folder_before = expense.folder_path
    if expense.category_id is None and row.category_id is not None:
        update_expense(ctx.session, ctx.settings, expense, category_id=row.category_id)
        if folder_before and expense.folder_path != folder_before:
            library = ctx.settings.library_dir
            ctx.journal.moved(library / folder_before, library / expense.folder_path)
            folder_before = expense.folder_path
    _assign(ctx, attachment, expense)
    _finish(ctx, expense, folder_before)
    ctx.result.attached.append(expense.id)


def _skip(ctx: _Context, _attachment: Attachment, _row: ConfirmRow) -> None:
    ctx.result.skipped += 1


HANDLERS: dict[str, Callable[[_Context, Attachment, ConfirmRow], None]] = {
    "create": _create,
    "attach": _attach,
    "skip": _skip,
}


def _confirm_row(ctx: _Context, refs: dict[str, int], row: ConfirmRow) -> None:
    attachment_id = refs.get(row.row_id)
    attachment = ctx.session.get(Attachment, attachment_id) if attachment_id else None
    if attachment is None:
        raise AppError(f"导入行不存在或已处理：{row.row_id}")
    with _file_errors(attachment.original_name):
        _require(row.row_id not in ctx.seen, "同一行不能重复提交")
        ctx.seen.add(row.row_id)
        HANDLERS[row.action](ctx, attachment, row)


def confirm_rows(
    session: Session, settings: Settings, refs: dict[str, int], rows: list[ConfirmRow]
) -> ConfirmResult:
    """逐行确认；失败时撤销已做的文件移动后抛出，调用方负责回滚数据库事务。"""
    ctx = _Context(session, settings)
    try:
        for row in rows:
            _confirm_row(ctx, refs, row)
    except Exception:
        ctx.journal.undo()
        raise
    return ctx.result
