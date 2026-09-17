"""导入确认（按凭证组）：新建记录 / 挂到已有记录 / 留在待归属。

整个请求原子：任一组失败时撤销已做的文件移动并抛出中文错误，调用方负责回滚数据库事务。
"""

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from invoice_sorting.attachments.storage import (
    absolute_path,
    assign_attachment,
    relocate_attachment,
)
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.common.errors import AppError
from invoice_sorting.config import Settings
from invoice_sorting.db.models import Attachment, Expense
from invoice_sorting.expenses.service import (
    create_expense,
    get_expense_or_404,
    refresh_expense,
    remember_invoice_category,
)
from invoice_sorting.importer.attach_fill import fill_attach_target
from invoice_sorting.importer.group_summary import suggest_group_category
from invoice_sorting.importer.items import item_from_attachment
from invoice_sorting.importer.journal import FsJournal
from invoice_sorting.importer.schemas import ConfirmGroup

logger = logging.getLogger(__name__)

IMPORT_NOTE = "导入凭证"
CNY = "CNY"


@dataclass
class ConfirmResult:
    created: list[int] = field(default_factory=list)
    attached: list[int] = field(default_factory=list)
    skipped: int = 0  # 留在待归属的文件数

    def as_dict(self) -> dict[str, Any]:
        return {
            "created": list(self.created),
            "attached": list(dict.fromkeys(self.attached)),
            "skipped": self.skipped,
        }


@dataclass
class ConfirmContext:
    session: Session
    settings: Settings
    allowed_ids: set[int] | None  # None 表示不限制（自动确认）
    journal: FsJournal = field(default_factory=FsJournal)
    result: ConfirmResult = field(default_factory=ConfirmResult)
    seen: set[int] = field(default_factory=set)


def group_label(attachments: list[Attachment]) -> str:
    first = f"文件“{attachments[0].original_name}”"
    return first if len(attachments) == 1 else f"{first}等 {len(attachments)} 个"


@contextmanager
def _group_errors(label: str) -> Iterator[None]:
    try:
        yield
    except AppError as exc:
        raise AppError(f"{label}：{exc.message}", exc.status_code) from exc
    except Exception as exc:
        logger.exception("确认导入失败：%s", label)
        raise AppError(f"{label}：确认导入失败，请重试") from exc


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AppError(message)


def _load_one(ctx: ConfirmContext, attachment_id: int) -> Attachment:
    attachment = ctx.session.get(Attachment, attachment_id)
    if attachment is None:
        raise AppError(f"附件 #{attachment_id} 不存在或已处理")
    name = attachment.original_name
    if ctx.allowed_ids is not None and attachment_id not in ctx.allowed_ids:
        raise AppError(f"文件“{name}”：不属于本次导入或已处理")
    if attachment_id in ctx.seen:
        raise AppError(f"文件“{name}”：不能同时出现在多个组")
    if attachment.expense_id is not None:
        raise AppError(f"文件“{name}”：已归属到记录 #{attachment.expense_id}，请刷新后重试")
    ctx.seen.add(attachment_id)
    return attachment


def _apply_kinds(ctx: ConfirmContext, attachments: list[Attachment], group: ConfirmGroup) -> None:
    by_id = {str(attachment.id): attachment for attachment in attachments}
    for key, kind in group.kinds.items():
        attachment = by_id.get(key.strip())
        _require(attachment is not None, f"类型设置中的附件 #{key} 不在该组")
        if attachment.kind == kind:
            continue
        before = absolute_path(ctx.settings, attachment)
        attachment.kind = str(kind)
        relocate_attachment(ctx.session, ctx.settings, attachment)
        ctx.journal.moved(before, absolute_path(ctx.settings, attachment))


def _require_single_invoice(attachments: list[Attachment]) -> None:
    invoices = [item for item in attachments if item.kind == AttachmentKind.INVOICE]
    if len(invoices) > 1:
        names = "、".join(f"“{item.original_name}”" for item in invoices)
        raise AppError(f"每组最多一张发票：{names}")


def _assign(ctx: ConfirmContext, attachment: Attachment, expense: Expense) -> None:
    before = absolute_path(ctx.settings, attachment)
    assign_attachment(ctx.session, ctx.settings, attachment, expense)
    ctx.journal.moved(before, absolute_path(ctx.settings, attachment))
    if attachment.evidence_data is not None:
        attachment.evidence_data.confirmed = True
    if attachment.invoice_data is not None:
        attachment.invoice_data.confirmed = True


def _finish(
    ctx: ConfirmContext, expense: Expense, attachments: list[Attachment], folder_before: str
) -> None:
    for attachment in attachments:
        _assign(ctx, attachment, expense)
    refresh_expense(ctx.session, ctx.settings, expense, note=IMPORT_NOTE)
    after = expense.folder_path
    if folder_before and after and folder_before != after:
        library = ctx.settings.library_dir
        ctx.journal.moved(library / folder_before, library / after)


def _remember_if_user_changed(
    ctx: ConfirmContext, attachments: list[Attachment], group: ConfirmGroup
) -> None:
    """用户在确认表中改了系统建议的分类时，才记住“商品/商家 → 分类”。"""
    if group.category_id is None:
        return
    items = tuple(item_from_attachment(attachment) for attachment in attachments)
    suggested = suggest_group_category(
        ctx.session, items, group.merchant or "", group.summary or ""
    )
    if suggested == group.category_id:
        return
    for attachment in attachments:
        if attachment.invoice_data is not None:
            remember_invoice_category(ctx.session, attachment.invoice_data, group.category_id)


def _create(ctx: ConfirmContext, attachments: list[Attachment], group: ConfirmGroup) -> None:
    exempt = bool(group.invoice_exempt)
    _require(group.spent_on is not None, "请填写支出日期")
    _require(group.amount_cents is not None, "请填写人民币金额" if exempt else "请填写金额")
    _require(bool(group.merchant), "请填写商家")
    expense = create_expense(
        ctx.session,
        ctx.settings,
        spent_on=group.spent_on,
        amount_cents=group.amount_cents,
        merchant=group.merchant,
        summary=group.summary or "",
        category_id=group.category_id,
        project_id=group.project_id,
        is_online=bool(group.is_online),
        invoice_exempt=exempt,
        currency=group.currency or CNY,
        original_amount_cents=group.original_amount_cents,
    )
    folder_before = expense.folder_path
    if folder_before:
        ctx.journal.created_dir(ctx.settings.library_dir / folder_before)
    _remember_if_user_changed(ctx, attachments, group)
    _finish(ctx, expense, attachments, folder_before)
    ctx.result.created.append(expense.id)


def _attach(ctx: ConfirmContext, attachments: list[Attachment], group: ConfirmGroup) -> None:
    _require(group.expense_id is not None, "挂到已有记录时需要选择记录")
    expense = get_expense_or_404(ctx.session, group.expense_id)
    folder_before = fill_attach_target(ctx.session, ctx.settings, ctx.journal, expense, group)
    _finish(ctx, expense, attachments, folder_before)
    ctx.result.attached.append(expense.id)


def _skip(ctx: ConfirmContext, attachments: list[Attachment], _group: ConfirmGroup) -> None:
    ctx.result.skipped += len(attachments)


HANDLERS: dict[str, Callable[[ConfirmContext, list[Attachment], ConfirmGroup], None]] = {
    "create": _create,
    "attach": _attach,
    "skip": _skip,
}


def _confirm_group(ctx: ConfirmContext, group: ConfirmGroup) -> None:
    attachments = [_load_one(ctx, attachment_id) for attachment_id in group.attachment_ids]
    with _group_errors(group_label(attachments)):
        _apply_kinds(ctx, attachments, group)
        _require_single_invoice(attachments)
        HANDLERS[group.action](ctx, attachments, group)


def confirm_groups(
    session: Session,
    settings: Settings,
    allowed_ids: set[int] | None,
    groups: list[ConfirmGroup],
) -> ConfirmResult:
    """逐组确认；失败时撤销已做的文件移动后抛出，调用方负责回滚数据库事务。"""
    ctx = ConfirmContext(session, settings, allowed_ids)
    try:
        for group in groups:
            _confirm_group(ctx, group)
    except Exception:
        ctx.journal.undo()
        raise
    return ctx.result
