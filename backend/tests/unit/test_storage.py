"""文件库：入库、魔数校验、去重、命名、移动、回收站。"""

from datetime import date
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from PIL import Image
from sqlalchemy import select

from invoice_sorting.attachments.storage import (
    DuplicateFileError,
    absolute_path,
    assign_attachment,
    attachment_file_name,
    guess_kind,
    sha256_of,
    store_file,
    sync_expense_folder,
    trash_attachment,
)
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.common.errors import AppError, ConflictError
from invoice_sorting.config import MAX_UPLOAD_BYTES
from invoice_sorting.db.models import Attachment, Category, InvoiceData
from invoice_sorting.expenses.service import create_expense, update_expense


def make_pdf(path: Path) -> Path:
    doc = pdfium.PdfDocument.new()
    doc.new_page(200, 300)
    doc.save(str(path))
    return path


def make_png(path: Path, color: str = "red") -> Path:
    Image.new("RGB", (40, 30), color).save(path)
    return path


def category_id(session, name: str) -> int:
    return session.scalar(select(Category.id).where(Category.name == name))


@pytest.fixture
def expense(session, settings):
    return create_expense(
        session,
        settings,
        spent_on=date(2026, 9, 15),
        amount_cents=96000,
        merchant="京东××店",
        category_id=category_id(session, "易耗品"),
    )


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("电子发票.pdf", AttachmentKind.INVOICE),
        ("Invoice_123.PDF", AttachmentKind.INVOICE),
        ("dzfp_2026.pdf", AttachmentKind.INVOICE),
        ("订单截图.png", AttachmentKind.ORDER),
        ("商品明细.jpg", AttachmentKind.ORDER),
        ("采购清单.xlsx", AttachmentKind.ORDER),
        ("支付记录.jpg", AttachmentKind.PAYMENT),
        ("微信账单.png", AttachmentKind.PAYMENT),
        ("pay_screen.png", AttachmentKind.PAYMENT),
        ("验收单.pdf", AttachmentKind.ACCEPTANCE),
        ("采购合同.pdf", AttachmentKind.CONTRACT),
        ("服务协议.pdf", AttachmentKind.CONTRACT),
        ("申购单.pdf", AttachmentKind.APPLICATION),
        ("滴滴行程单.pdf", AttachmentKind.ITINERARY),
        ("工作餐单.jpg", AttachmentKind.MEAL_FORM),
        ("会议签到表.pdf", AttachmentKind.MEETING),
        ("软件服务报账单.pdf", AttachmentKind.SOFTWARE_FORM),
        ("情况说明.docx", AttachmentKind.STATEMENT),
        ("IMG_0001.HEIC", AttachmentKind.OTHER),
    ],
)
def test_guess_kind_by_keywords(name, kind):
    assert guess_kind(name) is kind


def test_sha256_of_matches_known_digest(tmp_path):
    path = tmp_path / "a.txt"
    path.write_bytes(b"abc")
    assert sha256_of(path) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_store_file_unassigned_goes_to_pending_folder(session, settings, tmp_path):
    src = make_png(tmp_path / "订单截图.png")
    original = src.read_bytes()

    attachment = store_file(session, settings, src, "订单截图.png", AttachmentKind.ORDER)

    assert attachment.id is not None
    assert attachment.expense_id is None
    assert attachment.file_path.startswith("文件库/待归属/")
    assert attachment.mime == "image/png"
    assert attachment.size == len(original)
    assert absolute_path(settings, attachment).read_bytes() == original
    assert src.read_bytes() == original  # 原始文件不修改


def test_store_file_into_expense_folder_uses_blueprint_naming(session, settings, tmp_path, expense):
    first = store_file(
        session, settings, make_png(tmp_path / "o1.png"), "o1.png", AttachmentKind.ORDER, expense
    )
    second = store_file(
        session,
        settings,
        make_png(tmp_path / "o2.png", "blue"),
        "o2.png",
        AttachmentKind.ORDER,
        expense,
    )

    assert expense.folder_path == "2026/09/20260915_京东××店_易耗品_960.00_E" + f"{expense.id:04d}"
    assert first.file_path == f"文件库/{expense.folder_path}/订单明细_1.png"
    assert Path(second.file_path).name == "订单明细_2.png"
    assert attachment_file_name(second) == "订单明细_2.png"
    assert absolute_path(settings, second).is_file()


def test_attachment_file_name_prefers_invoice_number(session, settings, tmp_path, expense):
    attachment = store_file(
        session, settings, make_pdf(tmp_path / "fp.pdf"), "fp.pdf", AttachmentKind.INVOICE, expense
    )
    attachment.invoice_data = InvoiceData(invoice_no="24312000000012345678")
    assert attachment_file_name(attachment) == "发票_24312000000012345678.pdf"


def test_store_file_rejects_duplicate_hash(session, settings, tmp_path, expense):
    src = make_pdf(tmp_path / "a.pdf")
    existing = store_file(session, settings, src, "a.pdf", AttachmentKind.INVOICE, expense)
    copy = tmp_path / "copy.pdf"
    copy.write_bytes(src.read_bytes())

    with pytest.raises(DuplicateFileError) as info:
        store_file(session, settings, copy, "copy.pdf")

    assert isinstance(info.value, ConflictError)
    assert info.value.existing.id == existing.id
    assert f"记录 #{expense.id}" in info.value.message


@pytest.mark.parametrize(
    ("content", "name", "mime"),
    [
        (b"\xff\xd8\xff\xe0" + b"0" * 20, "a.jpg", "image/jpeg"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"0" * 10, "a.webp", "image/webp"),
        (b"\x00\x00\x00\x18ftypheic" + b"0" * 10, "a.heic", "image/heic"),
        (b"PK\x03\x04" + b"0" * 20, "a.ofd", "application/ofd"),
        (b"PK\x03\x04" + b"1" * 20, "a.zip", "application/zip"),
        ("﻿<?xml version='1.0'?><a>发票</a>".encode(), "a.xml", "application/xml"),
    ],
)
def test_store_file_accepts_supported_magic(session, settings, tmp_path, content, name, mime):
    src = tmp_path / name
    src.write_bytes(content)
    assert store_file(session, settings, src, name).mime == mime


@pytest.mark.parametrize(
    "content", [b"MZ\x90\x00 executable", b"plain text pretending", b"GIF89a....."]
)
def test_store_file_rejects_unsupported_type(session, settings, tmp_path, content):
    src = tmp_path / "evil.pdf"
    src.write_bytes(content)
    with pytest.raises(AppError, match="不支持"):
        store_file(session, settings, src, "evil.pdf")


def test_store_file_rejects_empty_and_oversized(session, settings, tmp_path):
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    with pytest.raises(AppError, match="为空"):
        store_file(session, settings, empty, "empty.pdf")

    big = tmp_path / "big.pdf"
    with big.open("wb") as handle:
        handle.write(b"%PDF-1.4\n")
        handle.truncate(MAX_UPLOAD_BYTES + 1)
    with pytest.raises(AppError, match="30MB"):
        store_file(session, settings, big, "big.pdf")


def test_folder_renames_when_expense_changes_and_files_stay_readable(
    session, settings, tmp_path, expense
):
    attachment = store_file(
        session, settings, make_pdf(tmp_path / "a.pdf"), "a.pdf", AttachmentKind.INVOICE, expense
    )
    old_folder = settings.library_dir / expense.folder_path

    update_expense(session, settings, expense, amount_cents=123456, merchant="新:商家/名?")

    assert not old_folder.exists()
    assert expense.folder_path.endswith(f"_新_商家_名__易耗品_1234.56_E{expense.id:04d}")
    assert (settings.library_dir / expense.folder_path).is_dir()
    assert absolute_path(settings, attachment).is_file()
    assert attachment.file_path.startswith(f"文件库/{expense.folder_path}/")


def test_folder_moves_to_new_month_and_truncates_merchant(session, settings, expense):
    update_expense(session, settings, expense, spent_on=date(2026, 10, 1), merchant="商" * 40)
    assert expense.folder_path.startswith("2026/10/20261001_" + "商" * 30 + "_易耗品")


def test_folder_name_conflict_appends_suffix(session, settings, expense):
    folder = expense.folder_path
    (settings.library_dir / folder).rename(settings.library_dir / (folder + "_tmp"))
    (settings.library_dir / folder).mkdir(parents=True)  # 被其他目录占用
    expense.folder_path = folder + "_tmp"

    sync_expense_folder(session, settings, expense)

    assert expense.folder_path == folder + "_2"


def test_assign_attachment_moves_between_pending_and_expense(session, settings, tmp_path, expense):
    attachment = store_file(session, settings, make_png(tmp_path / "pay.png"), "pay.png")

    assign_attachment(session, settings, attachment, expense)
    assert attachment.expense_id == expense.id
    assert attachment.file_path.startswith(f"文件库/{expense.folder_path}/")
    assert absolute_path(settings, attachment).is_file()

    assign_attachment(session, settings, attachment, None)
    assert attachment.expense_id is None
    assert attachment.file_path.startswith("文件库/待归属/")
    assert absolute_path(settings, attachment).is_file()


def test_trash_attachment_moves_file_and_deletes_records(session, settings, tmp_path, expense):
    attachment = store_file(
        session, settings, make_pdf(tmp_path / "a.pdf"), "a.pdf", AttachmentKind.INVOICE, expense
    )
    attachment.invoice_data = InvoiceData(invoice_no="123")
    session.flush()
    stored = absolute_path(settings, attachment)
    attachment_id = attachment.id

    trash_attachment(session, settings, attachment)

    assert not stored.exists()
    assert any(settings.trash_dir.rglob("*.pdf"))
    assert session.get(Attachment, attachment_id) is None
    assert session.scalar(select(InvoiceData).where(InvoiceData.invoice_no == "123")) is None
