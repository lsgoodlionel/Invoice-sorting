"""资料包命名规则（蓝图 8.2）：序号贯穿汇总表、打印 PDF 与文件名前缀。"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from invoice_sorting.attachments.filetypes import extension_for
from invoice_sorting.attachments.serializers import kind_label
from invoice_sorting.attachments.storage import safe_component
from invoice_sorting.common.constants import AttachmentKind, ExportLayout
from invoice_sorting.common.money import cents_to_yuan
from invoice_sorting.db.models import Attachment, Batch, Expense

MERCHANT_MAX_CHARS = 30
SUMMARY_NAME = "00_报销汇总表.xlsx"
PRINT_NAME = "01_打印版_全部材料.pdf"
INVOICE_DIR = "02_发票原件"
SUPPORT_DIR = "03_支撑材料"
FALLBACK_MERCHANT = "未填商家"

# 打印版合并顺序；同时用于附件清单的显示顺序
KIND_ORDER: tuple[AttachmentKind, ...] = (
    AttachmentKind.INVOICE,
    AttachmentKind.ORDER,
    AttachmentKind.PAYMENT,
    AttachmentKind.ACCEPTANCE,
    AttachmentKind.APPLICATION,
    AttachmentKind.CONTRACT,
    AttachmentKind.ITINERARY,
    AttachmentKind.MEAL_FORM,
    AttachmentKind.MEETING,
    AttachmentKind.SOFTWARE_FORM,
    AttachmentKind.STATEMENT,
    AttachmentKind.OTHER,
)


@dataclass(frozen=True)
class PackageItem:
    """资料包中的一条记录：序号 + 支出 + 按打印顺序排列的附件。"""

    seq: int
    expense: Expense
    attachments: tuple[Attachment, ...] = field(default_factory=tuple)


def kind_rank(kind: str) -> int:
    try:
        return KIND_ORDER.index(AttachmentKind(kind))
    except ValueError:
        return KIND_ORDER.index(AttachmentKind.OTHER)


def ordered_attachments(expense: Expense) -> tuple[Attachment, ...]:
    return tuple(sorted(expense.attachments, key=lambda item: (kind_rank(item.kind), item.id)))


def package_items(expenses: list[Expense]) -> list[PackageItem]:
    """按日期升序、id 升序编号，序号从 1 开始。"""
    ordered = sorted(expenses, key=lambda expense: (expense.spent_on, expense.id))
    return [
        PackageItem(seq=index, expense=expense, attachments=ordered_attachments(expense))
        for index, expense in enumerate(ordered, start=1)
    ]


def merchant_token(expense: Expense) -> str:
    return safe_component(expense.merchant or "")[:MERCHANT_MAX_CHARS] or FALLBACK_MERCHANT


def attachment_ext(attachment: Attachment) -> str:
    return extension_for(attachment.original_name, attachment.mime)


def invoice_original_name(item: PackageItem, attachment: Attachment) -> str:
    invoice = attachment.invoice_data
    token = safe_component(invoice.invoice_no) if invoice and invoice.invoice_no else ""
    amount = cents_to_yuan(item.expense.amount_cents)
    name = f"{item.seq:02d}_{amount}_{merchant_token(item.expense)}_{token or attachment.id}"
    return f"{INVOICE_DIR}/{name}{attachment_ext(attachment)}"


def support_name(item: PackageItem, attachment: Attachment, index: int, layout: str) -> str:
    """支撑材料在 ZIP 中的路径；index 为同一记录内同类附件的序号（从 1 开始）。"""
    label = kind_label(attachment.kind)
    ext = attachment_ext(attachment)
    group = (
        f"{item.seq:02d}_{merchant_token(item.expense)}_{cents_to_yuan(item.expense.amount_cents)}"
    )
    if ExportLayout(layout) == ExportLayout.BY_KIND:
        return f"{SUPPORT_DIR}/{label}/{group}_{index}{ext}"
    return f"{SUPPORT_DIR}/{group}/{label}_{index}{ext}"


def unique_name(name: str, used: set[str]) -> str:
    """ZIP 内同名时追加 `_2`、`_3`…，并登记到 used。"""
    candidate, stem, suffix, index = name, str(Path(name).with_suffix("")), Path(name).suffix, 2
    while candidate in used:
        candidate = f"{stem}_{index}{suffix}"
        index += 1
    used.add(candidate)
    return candidate


def package_title(batch: Batch) -> str:
    project = batch.project
    return safe_component(project.name if project else batch.name) or "批次"


def package_dir_name(batch: Batch, moment: datetime) -> str:
    batch_name = safe_component(batch.name) or f"批次{batch.id}"
    return f"{moment:%Y%m%d}_{package_title(batch)}_{batch_name}"


def package_file_name(batch: Batch, moment: datetime) -> str:
    return f"报销资料_{package_title(batch)}_{moment:%Y%m%d_%H%M%S}.zip"
