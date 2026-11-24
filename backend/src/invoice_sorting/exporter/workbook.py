"""资料包汇总表：Sheet“汇总”与“分类小计”。金额以分累加，写入时转 Decimal 元。"""

import io
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from invoice_sorting.attachments.serializers import kind_label
from invoice_sorting.common.constants import ChecklistLevel, ChecklistState
from invoice_sorting.db.models import Batch, Expense
from invoice_sorting.expenses.serializers import (
    display_item_name,
    first_invoice_issued_on,
    first_invoice_no,
)
from invoice_sorting.exporter.naming import PackageItem, kind_rank

AMOUNT_FORMAT = "#,##0.00"
LIST_SEPARATOR = "、"
NO_CATEGORY = "未分类"
SUMMARY_HEADERS = (
    "序号",
    "业务发生日期",
    "发票开票日期",
    "凭证填报日期",
    "商家",
    "摘要",
    "名称",
    "单价",
    "数量",
    "总价",
    "发票号",
    "分类",
    "设备与实验室平台申请",
    "附件清单",
    "缺项",
    "备注",
)
SUMMARY_WIDTHS = (6, 12, 12, 12, 24, 24, 28, 12, 8, 14, 24, 14, 18, 36, 24, 36)
UNIT_PRICE_COLUMN = SUMMARY_HEADERS.index("单价") + 1
AMOUNT_COLUMN = SUMMARY_HEADERS.index("总价") + 1
SUBTOTAL_HEADERS = ("分类", "是否需要平台申请", "清单数", "材料数", "金额")
SUBTOTAL_WIDTHS = (16, 18, 10, 10, 16)
HEADER_ROW = 2
BOLD = Font(bold=True)

NoteLookup = Callable[[int], str]


def cents_to_decimal(cents: int) -> Decimal:
    """分 → 元（Decimal，两位小数），避免浮点误差。"""
    return Decimal(cents).scaleb(-2)


def attachment_list(expense: Expense) -> str:
    kinds = sorted({attachment.kind for attachment in expense.attachments}, key=kind_rank)
    return LIST_SEPARATOR.join(kind_label(kind) for kind in kinds)


def missing_list(expense: Expense) -> str:
    missing = [
        item.attachment_kind
        for item in expense.checklist_items
        if item.level == ChecklistLevel.REQUIRED and item.state == ChecklistState.MISSING
    ]
    return LIST_SEPARATOR.join(kind_label(kind) for kind in sorted(missing, key=kind_rank))


def _note(expense: Expense, extra: str) -> str:
    return "；".join(part for part in (expense.note or "", extra) if part)


def _set_widths(sheet: Worksheet, widths: tuple[int, ...]) -> None:
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width


def _write_header(sheet: Worksheet, title: str, headers: tuple[str, ...]) -> None:
    sheet.cell(row=1, column=1, value=title).font = Font(bold=True, size=13)
    for column, header in enumerate(headers, start=1):
        cell = sheet.cell(row=HEADER_ROW, column=column, value=header)
        cell.font = BOLD
        cell.alignment = Alignment(horizontal="center")
    sheet.freeze_panes = f"A{HEADER_ROW + 1}"


def _summary_row(item: PackageItem, extra_note: str) -> tuple:
    expense = item.expense
    return (
        item.seq,
        expense.spent_on.isoformat(),
        first_invoice_issued_on(expense) or "",
        expense.created_at.date().isoformat(),
        expense.merchant,
        expense.summary,
        display_item_name(expense),
        cents_to_decimal(expense.unit_price_cents) if expense.unit_price_cents is not None else "",
        expense.quantity if expense.quantity is not None else "",
        cents_to_decimal(expense.amount_cents),
        first_invoice_no(expense) or "",
        expense.category.name if expense.category else NO_CATEGORY,
        (
            "是"
            if expense.category and expense.category.requires_lab_platform
            else "否"
            if expense.category
            else "未判定"
        ),
        attachment_list(expense),
        missing_list(expense),
        _note(expense, extra_note),
    )


def _write_summary(
    sheet: Worksheet, title: str, items: list[PackageItem], notes: NoteLookup
) -> None:
    _write_header(sheet, title, SUMMARY_HEADERS)
    for item in items:
        sheet.append(_summary_row(item, notes(item.expense.id)))
        if item.expense.unit_price_cents is not None:
            sheet.cell(row=sheet.max_row, column=UNIT_PRICE_COLUMN).number_format = AMOUNT_FORMAT
        sheet.cell(row=sheet.max_row, column=AMOUNT_COLUMN).number_format = AMOUNT_FORMAT
    total = sum(item.expense.amount_cents for item in items)
    total_row = [""] * len(SUMMARY_HEADERS)
    total_row[0] = "合计"
    total_row[SUMMARY_HEADERS.index("名称")] = f"清单 {len(items)} 条"
    material_count = sum(len(item.attachments) for item in items)
    total_row[SUMMARY_HEADERS.index("附件清单")] = f"材料 {material_count} 份"
    total_row[AMOUNT_COLUMN - 1] = cents_to_decimal(total)
    sheet.append(tuple(total_row))
    for column in range(1, len(SUMMARY_HEADERS) + 1):
        sheet.cell(row=sheet.max_row, column=column).font = BOLD
    sheet.cell(row=sheet.max_row, column=AMOUNT_COLUMN).number_format = AMOUNT_FORMAT
    _set_widths(sheet, SUMMARY_WIDTHS)


def category_subtotals(items: list[PackageItem]) -> list[tuple[str, bool | None, int, int, int]]:
    """(分类, 是否平台申请, 清单数, 材料数, 金额分)，按金额降序。"""
    groups: dict[str, tuple[bool | None, int, int, int]] = {}
    for item in items:
        expense = item.expense
        name = expense.category.name if expense.category else NO_CATEGORY
        required = bool(expense.category.requires_lab_platform) if expense.category else None
        _old_required, count, materials, cents = groups.get(name, (required, 0, 0, 0))
        groups[name] = (
            required,
            count + 1,
            materials + len(item.attachments),
            cents + expense.amount_cents,
        )
    rows = [
        (name, required, count, materials, cents)
        for name, (required, count, materials, cents) in groups.items()
    ]
    return sorted(rows, key=lambda row: (-row[4], row[0]))


def _write_subtotals(sheet: Worksheet, title: str, items: list[PackageItem]) -> None:
    _write_header(sheet, title, SUBTOTAL_HEADERS)
    for name, required, count, materials, cents in category_subtotals(items):
        platform_label = "未判定" if required is None else "是" if required else "否"
        sheet.append((name, platform_label, count, materials, cents_to_decimal(cents)))
        sheet.cell(row=sheet.max_row, column=5).number_format = AMOUNT_FORMAT
    total = sum(item.expense.amount_cents for item in items)
    material_count = sum(len(item.attachments) for item in items)
    sheet.append(("合计", "", len(items), material_count, cents_to_decimal(total)))
    for column in range(1, 6):
        sheet.cell(row=sheet.max_row, column=column).font = BOLD
    sheet.cell(row=sheet.max_row, column=5).number_format = AMOUNT_FORMAT
    _set_widths(sheet, SUBTOTAL_WIDTHS)


def _category_groups(items: list[PackageItem]) -> list[tuple[str, list[PackageItem]]]:
    groups: dict[str, list[PackageItem]] = {}
    for item in items:
        name = item.expense.category.name if item.expense.category else NO_CATEGORY
        groups.setdefault(name, []).append(item)
    return sorted(groups.items(), key=lambda pair: pair[0])


def _sheet_name(name: str, used: set[str]) -> str:
    cleaned = "".join("_" if char in "[]:*?/\\" else char for char in name).strip() or NO_CATEGORY
    base = f"分类-{cleaned}"[:31]
    candidate, index = base, 2
    while candidate in used:
        suffix = f"-{index}"
        candidate = f"{base[: 31 - len(suffix)]}{suffix}"
        index += 1
    used.add(candidate)
    return candidate


def build_summary_workbook(
    batch: Batch, items: list[PackageItem], notes: NoteLookup, moment: datetime
) -> bytes:
    project = batch.project
    project_name = project.name if project else "无项目"
    title = f"批次：{batch.name}　项目：{project_name}　导出时间：{moment:%Y-%m-%d %H:%M}"
    workbook = Workbook()
    workbook.active.title = "汇总"
    _write_summary(workbook.active, title, items, notes)
    _write_subtotals(workbook.create_sheet("分类小计"), title, items)
    used = {sheet.title for sheet in workbook.worksheets}
    for category_name, category_items in _category_groups(items):
        sheet = workbook.create_sheet(_sheet_name(category_name, used))
        _write_summary(sheet, f"{title}　分类：{category_name}", category_items, notes)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
