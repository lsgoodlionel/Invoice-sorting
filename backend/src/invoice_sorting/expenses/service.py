"""支出记录服务：新建、修改、自动/手动状态、软删除、商家分类记忆。"""

import re
from typing import Any

from sqlalchemy.orm import Session

from invoice_sorting.attachments.storage import sync_expense_folder, trash_expense_files
from invoice_sorting.checklist.service import compute_checklist, required_missing_count
from invoice_sorting.common.constants import AttachmentKind, BatchStatus, ExpenseStatus
from invoice_sorting.common.errors import AppError, ConflictError, NotFoundError
from invoice_sorting.config import Settings
from invoice_sorting.db.models import (
    Batch,
    Category,
    Expense,
    InvoiceData,
    ItemMemory,
    MerchantMemory,
    Project,
    StatusEvent,
    now,
)
from invoice_sorting.expenses.status import derive_status

EDITABLE_FIELDS = frozenset(
    {
        "spent_on",
        "amount_cents",
        "merchant",
        "summary",
        "category_id",
        "project_id",
        "pay_method",
        "is_online",
        "note",
        "invoice_exempt",
        "currency",
        "original_amount_cents",
    }
)
CNY = "CNY"
EXEMPT_EVIDENCE_KINDS = frozenset({AttachmentKind.ORDER, AttachmentKind.PAYMENT})
SENT_BATCH_STATUSES = frozenset({BatchStatus.SENT, BatchStatus.PARTIAL, BatchStatus.RECEIVED})
CREATED_NOTE = "创建"


def _validate_fields(session: Session, fields: dict[str, Any]) -> None:
    unknown = set(fields) - EDITABLE_FIELDS
    if unknown:
        raise AppError(f"不支持修改的字段：{'、'.join(sorted(unknown))}")
    if fields.get("amount_cents") is not None and fields["amount_cents"] < 0:
        raise AppError("金额不能为负数")
    category_id = fields.get("category_id")
    if category_id is not None and session.get(Category, category_id) is None:
        raise NotFoundError("分类")
    project_id = fields.get("project_id")
    if project_id is not None and session.get(Project, project_id) is None:
        raise NotFoundError("经费项目")


def _record_status(
    session: Session, expense: Expense, status: ExpenseStatus, *, manual: bool, note: str
) -> None:
    previous = expense.status
    expense.status = str(status)
    event = StatusEvent(
        from_status=previous, to_status=str(status), is_manual=manual, note=note, at=now()
    )
    expense.status_events.append(event)
    session.flush()


def _invoices(expense: Expense) -> list[InvoiceData]:
    return [
        attachment.invoice_data
        for attachment in expense.attachments
        if attachment.kind == AttachmentKind.INVOICE and attachment.invoice_data is not None
    ]


def get_expense_or_404(session: Session, expense_id: int) -> Expense:
    """读取未删除的支出记录，不存在时抛 NotFoundError。"""
    expense = session.get(Expense, expense_id)
    if expense is None or expense.deleted:
        raise NotFoundError("支出记录")
    return expense


ITEM_COUNT_SUFFIX = re.compile(r"等\d+项$")


def normalize_item_name(item_summary: str) -> str:
    """“收纳盒等2项” → “收纳盒”，用于按商品记忆分类。"""
    return ITEM_COUNT_SUFFIX.sub("", (item_summary or "").strip()).strip()


def remember_item_category(session: Session, item_summary: str, category_id: int) -> None:
    """记住“发票商品名称 → 分类”，用于导入时的分类建议。"""
    name = normalize_item_name(item_summary)
    if not name:
        return
    memory = session.get(ItemMemory, name)
    if memory is None:
        session.add(ItemMemory(item_name=name, category_id=category_id, updated_at=now()))
    else:
        memory.category_id = category_id
        memory.updated_at = now()
    session.flush()


def remember_invoice_category(session: Session, invoice: InvoiceData, category_id: int) -> None:
    """同时记住该发票的销售方与商品名称对应的分类。"""
    if invoice.seller_name:
        remember_merchant_category(session, invoice.seller_name, category_id)
    if invoice.item_summary:
        remember_item_category(session, invoice.item_summary, category_id)


def remember_merchant_category(session: Session, seller_name: str, category_id: int) -> None:
    """记住“销售方 → 分类”，用于导入时的分类建议。"""
    name = seller_name.strip()
    if not name:
        return
    memory = session.get(MerchantMemory, name)
    if memory is None:
        session.add(MerchantMemory(seller_name=name, category_id=category_id, updated_at=now()))
    else:
        memory.category_id = category_id
        memory.updated_at = now()
    session.flush()


def _normalize_currency(expense: Expense) -> None:
    """人民币记录不保留原币金额。"""
    if not expense.currency:
        expense.currency = CNY
    if expense.currency == CNY:
        expense.original_amount_cents = None


def create_expense(session: Session, settings: Settings, **fields: Any) -> Expense:
    _validate_fields(session, fields)
    expense = Expense(status=str(ExpenseStatus.SPENT), status_manual=False, **fields)
    _normalize_currency(expense)
    session.add(expense)
    session.flush()
    expense.status_events.append(
        StatusEvent(from_status=None, to_status=expense.status, note=CREATED_NOTE, at=now())
    )
    return refresh_expense(session, settings, expense)


def update_expense(
    session: Session, settings: Settings, expense: Expense, **fields: Any
) -> Expense:
    _validate_fields(session, fields)
    for name, value in fields.items():
        setattr(expense, name, value)
    _normalize_currency(expense)
    session.flush()
    if fields.get("category_id") is not None:
        for invoice in _invoices(expense):
            remember_invoice_category(session, invoice, fields["category_id"])
    return refresh_expense(session, settings, expense)


def has_confirmed_invoice(expense: Expense) -> bool:
    return any(
        attachment.kind == AttachmentKind.INVOICE
        and (attachment.invoice_data is None or attachment.invoice_data.confirmed)
        for attachment in expense.attachments
    )


def _in_sent_batch(session: Session, expense: Expense) -> bool:
    if expense.batch_id is None:
        return False
    batch = session.get(Batch, expense.batch_id)
    return batch is not None and batch.status in SENT_BATCH_STATUSES


def has_exempt_evidence(expense: Expense) -> bool:
    """免发票记录的“已收凭证”：有订单/收据或支付记录任一项。"""
    return any(attachment.kind in EXEMPT_EVIDENCE_KINDS for attachment in expense.attachments)


def _auto_status(session: Session, expense: Expense) -> ExpenseStatus:
    return derive_status(
        has_invoice=has_confirmed_invoice(expense),
        required_missing=required_missing_count(expense),
        in_sent_batch=_in_sent_batch(session, expense),
        reimbursed=expense.reimbursed_on is not None,
        invoice_exempt=bool(expense.invoice_exempt),
        has_exempt_evidence=has_exempt_evidence(expense),
    )


def refresh_expense(
    session: Session,
    settings: Settings,
    expense: Expense,
    *,
    note: str = "",
    clear_manual: bool = False,
) -> Expense:
    """重算清单 → （可选）取消手动 → 自动推导状态 → 同步文件夹名。"""
    session.flush()
    session.refresh(expense, attribute_names=["attachments", "batch", "category", "project"])
    compute_checklist(session, expense)
    if clear_manual:
        expense.status_manual = False
    is_void = expense.status == ExpenseStatus.VOID
    if not expense.status_manual and (clear_manual or not is_void):
        status = _auto_status(session, expense)
        if status != expense.status:
            _record_status(session, expense, status, manual=False, note=note)
        if is_void:
            expense.void_reason = ""
    sync_expense_folder(session, settings, expense)
    session.flush()
    return expense


def set_status(
    session: Session,
    settings: Settings,
    expense: Expense,
    status: ExpenseStatus | None,
    note: str = "",
) -> Expense:
    """手动设置状态；None 表示取消手动并恢复自动。作废必须填写原因。"""
    if status is None:
        return refresh_expense(session, settings, expense, note=note, clear_manual=True)
    note = note.strip()
    if status == ExpenseStatus.VOID and not note:
        raise AppError("设为“不报销/作废”需要填写原因")
    if status == ExpenseStatus.VOID:
        detach_from_draft_batch(expense, action="作废")
    if status != expense.status or not expense.status_manual:
        _record_status(session, expense, status, manual=True, note=note)
    expense.status_manual = True
    expense.void_reason = note if status == ExpenseStatus.VOID else ""
    return refresh_expense(session, settings, expense)


def detach_from_draft_batch(expense: Expense, *, action: str) -> None:
    """记录在草稿批次中则移出；批次已外发时拒绝操作。"""
    batch = expense.batch
    if batch is None:
        return
    if batch.status != BatchStatus.DRAFT:
        raise ConflictError(f"该记录所在批次『{batch.name}』已外发，请先重新打开批次再{action}")
    expense.batch_id = None
    expense.batch = None


def soft_delete_expense(session: Session, settings: Settings, expense: Expense) -> None:
    """软删除：移出草稿批次，附件文件移入回收站并删除附件记录（便于之后重新导入同一文件）。"""
    detach_from_draft_batch(expense, action="删除")
    trash_expense_files(session, settings, expense)
    for attachment in list(expense.attachments):
        session.delete(attachment)
    expense.deleted = True
    session.flush()
