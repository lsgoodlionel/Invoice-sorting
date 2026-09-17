"""支出记录服务：自动状态、手动覆盖、作废、软删除、商家记忆（T06/T07/T15）。"""

from datetime import date
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import select

from invoice_sorting.attachments.storage import absolute_path, store_file, trash_attachment
from invoice_sorting.common.constants import AttachmentKind, ExpenseStatus
from invoice_sorting.common.errors import AppError, NotFoundError
from invoice_sorting.db.models import Batch, Category, InvoiceData, MerchantMemory
from invoice_sorting.expenses.service import (
    create_expense,
    refresh_expense,
    remember_merchant_category,
    set_status,
    soft_delete_expense,
    update_expense,
)


def category_id(session, name: str) -> int:
    return session.scalar(select(Category.id).where(Category.name == name))


def add_file(session, settings, tmp_path: Path, expense, kind: AttachmentKind, color: str):
    src = tmp_path / f"{kind}_{color}.png"
    Image.new("RGB", (10, 10), color).save(src)
    return store_file(session, settings, src, src.name, kind, expense)


@pytest.fixture
def expense(session, settings):
    return create_expense(
        session,
        settings,
        spent_on=date(2026, 9, 15),
        amount_cents=96000,
        merchant="京东",
        summary="鼠标×2",
        category_id=category_id(session, "易耗品"),
    )


def test_create_expense_starts_spent_with_timeline_and_folder(session, settings, expense):
    assert expense.status == ExpenseStatus.SPENT
    assert expense.status_manual is False
    assert [e.to_status for e in expense.status_events] == ["spent"]
    assert (settings.library_dir / expense.folder_path).is_dir()


def test_create_expense_rejects_unknown_category(session, settings):
    with pytest.raises(NotFoundError):
        create_expense(
            session, settings, spent_on=date(2026, 9, 1), amount_cents=1, category_id=9999
        )


def test_update_expense_rejects_unknown_field(session, settings, expense):
    with pytest.raises(AppError):
        update_expense(session, settings, expense, status="void")


def test_invoice_moves_to_invoiced_then_complete(session, settings, tmp_path, expense):
    add_file(session, settings, tmp_path, expense, AttachmentKind.INVOICE, "red")
    refresh_expense(session, settings, expense)
    assert expense.status == ExpenseStatus.INVOICED

    add_file(session, settings, tmp_path, expense, AttachmentKind.ORDER, "green")
    refresh_expense(session, settings, expense)
    assert expense.status == ExpenseStatus.INVOICED

    acceptance = [i for i in expense.checklist_items if i.attachment_kind == "acceptance"][0]
    acceptance.state = "not_needed"
    refresh_expense(session, settings, expense)
    assert expense.status == ExpenseStatus.COMPLETE
    assert [e.to_status for e in expense.status_events] == ["spent", "invoiced", "complete"]
    assert all(e.is_manual is False for e in expense.status_events)


def test_unconfirmed_parsed_invoice_does_not_count(session, settings, tmp_path, expense):
    invoice = add_file(session, settings, tmp_path, expense, AttachmentKind.INVOICE, "red")
    invoice.invoice_data = InvoiceData(invoice_no="1", confirmed=False)
    refresh_expense(session, settings, expense)
    assert expense.status == ExpenseStatus.SPENT

    invoice.invoice_data.confirmed = True
    refresh_expense(session, settings, expense)
    assert expense.status == ExpenseStatus.INVOICED


def test_manual_status_is_not_reverted_when_attachment_removed(
    session, settings, tmp_path, expense
):
    order = add_file(session, settings, tmp_path, expense, AttachmentKind.ORDER, "green")
    set_status(session, settings, expense, ExpenseStatus.COMPLETE, note="已线下补齐")
    assert expense.status_manual is True
    assert expense.status_events[-1].is_manual is True

    trash_attachment(session, settings, order)
    refresh_expense(session, settings, expense)

    assert expense.status == ExpenseStatus.COMPLETE
    order_item = [i for i in expense.checklist_items if i.attachment_kind == "order"][0]
    assert order_item.state == "missing"


def test_clearing_manual_status_recomputes(session, settings, expense):
    set_status(session, settings, expense, ExpenseStatus.COMPLETE)
    set_status(session, settings, expense, None)
    assert expense.status_manual is False
    assert expense.status == ExpenseStatus.SPENT


def test_void_requires_reason_and_is_sticky(session, settings, expense):
    with pytest.raises(AppError, match="原因"):
        set_status(session, settings, expense, ExpenseStatus.VOID, note="  ")

    set_status(session, settings, expense, ExpenseStatus.VOID, note="个人承担")
    assert expense.void_reason == "个人承担"
    refresh_expense(session, settings, expense)
    assert expense.status == ExpenseStatus.VOID

    set_status(session, settings, expense, None)
    assert expense.status == ExpenseStatus.SPENT
    assert expense.void_reason == ""


def test_sent_batch_and_reimbursed_drive_status(session, settings, expense):
    batch = Batch(name="第1批", status="sent")
    session.add(batch)
    session.flush()
    expense.batch_id = batch.id
    refresh_expense(session, settings, expense)
    assert expense.status == ExpenseStatus.SENT

    expense.reimbursed_on = date(2026, 11, 1)
    refresh_expense(session, settings, expense, note="批次到账")
    assert expense.status == ExpenseStatus.REIMBURSED
    assert expense.status_events[-1].note == "批次到账"


def test_draft_batch_does_not_mean_sent(session, settings, expense):
    batch = Batch(name="草稿", status="draft")
    session.add(batch)
    session.flush()
    expense.batch_id = batch.id
    refresh_expense(session, settings, expense)
    assert expense.status == ExpenseStatus.SPENT


def test_soft_delete_moves_files_to_trash(session, settings, tmp_path, expense):
    attachment = add_file(session, settings, tmp_path, expense, AttachmentKind.ORDER, "blue")
    original = absolute_path(settings, attachment)

    soft_delete_expense(session, settings, expense)

    assert expense.deleted is True
    assert not original.exists()
    assert absolute_path(settings, attachment).is_file()
    assert settings.trash_dir in absolute_path(settings, attachment).parents


def test_remember_merchant_category_upserts(session):
    first = category_id(session, "易耗品")
    second = category_id(session, "办公用品")
    remember_merchant_category(session, "上海示例文具店", first)
    remember_merchant_category(session, "上海示例文具店", second)
    remember_merchant_category(session, "  ", second)
    memory = session.get(MerchantMemory, "上海示例文具店")
    assert memory.category_id == second
    assert session.scalars(select(MerchantMemory)).all() == [memory]


def test_changing_category_remembers_invoice_seller(session, settings, tmp_path, expense):
    invoice = add_file(session, settings, tmp_path, expense, AttachmentKind.INVOICE, "red")
    invoice.invoice_data = InvoiceData(seller_name="北京京东世纪信息技术有限公司")
    session.flush()

    update_expense(session, settings, expense, category_id=category_id(session, "办公用品"))

    # 京东等综合电商平台什么都卖，不记“商家 → 分类”
    assert session.get(MerchantMemory, "北京京东世纪信息技术有限公司") is None
