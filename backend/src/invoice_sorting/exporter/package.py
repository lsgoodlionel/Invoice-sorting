"""资料包 ZIP 生成（蓝图 8.2）：先写临时文件再原子改名，每次导出生成新文件。"""

import logging
import os
import zipfile
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from invoice_sorting.attachments.storage import absolute_path, sha256_of
from invoice_sorting.batches.serializers import active_expenses
from invoice_sorting.common.constants import AttachmentKind, ExportLayout
from invoice_sorting.common.errors import AppError
from invoice_sorting.config import Settings
from invoice_sorting.db.models import Attachment, Batch, ExportRecord, now
from invoice_sorting.exporter.naming import (
    PRINT_NAME,
    SUMMARY_NAME,
    PackageItem,
    invoice_original_name,
    package_dir_name,
    package_file_name,
    package_items,
    support_name,
    unique_name,
)
from invoice_sorting.exporter.print_pdf import build_print_pdf
from invoice_sorting.exporter.workbook import build_summary_workbook

logger = logging.getLogger(__name__)

TEMP_SUFFIX = ".part"


def _free_file(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    stem, suffix, index = candidate.stem, candidate.suffix, 2
    while candidate.exists():
        candidate = directory / f"{stem}_{index}{suffix}"
        index += 1
    return candidate


def _file_entries(
    settings: Settings, items: list[PackageItem], layout: ExportLayout
) -> list[tuple[Path, str]]:
    """(源文件, ZIP 内路径)：发票原件进 02，其余进 03。缺失的源文件跳过并记录日志。"""
    entries: list[tuple[Path, str]] = []
    used: set[str] = set()
    for item in items:
        counters: dict[str, int] = {}
        for attachment in item.attachments:
            source = absolute_path(settings, attachment)
            if not source.is_file():
                logger.warning("附件 #%s 文件缺失，未打包：%s", attachment.id, source)
                continue
            if attachment.kind == AttachmentKind.INVOICE:
                name = invoice_original_name(item, attachment)
            else:
                counters[attachment.kind] = counters.get(attachment.kind, 0) + 1
                name = support_name(item, attachment, counters[attachment.kind], layout)
            entries.append((source, unique_name(name, used)))
    return entries


def _write_zip(target: Path, members: dict[str, bytes], files: list[tuple[Path, str]]) -> None:
    temp = target.with_name(target.name + TEMP_SUFFIX)
    try:
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in members.items():
                archive.writestr(name, content)
            for source, name in files:
                archive.write(source, arcname=name)
        os.replace(temp, target)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def export_batch(
    session: Session,
    settings: Settings,
    batch: Batch,
    layout: ExportLayout,
    moment: datetime | None = None,
) -> ExportRecord:
    """生成资料包并写入导出记录。空批次抛 AppError。"""
    expenses = active_expenses(batch)
    if not expenses:
        raise AppError("空批次不能导出资料包")
    moment = moment or now()
    items = package_items(expenses)

    def resolve(attachment: Attachment) -> Path:
        return absolute_path(settings, attachment)

    printed = build_print_pdf(items, resolve)
    workbook = build_summary_workbook(batch, items, printed.notes_for, moment)
    directory = settings.packages_dir / package_dir_name(batch, moment)
    directory.mkdir(parents=True, exist_ok=True)
    target = _free_file(directory, package_file_name(batch, moment))
    members = {SUMMARY_NAME: workbook, PRINT_NAME: printed.pdf_bytes}
    _write_zip(target, members, _file_entries(settings, items, ExportLayout(layout)))
    record = ExportRecord(
        batch_id=batch.id,
        layout=str(layout),
        file_path=target.relative_to(settings.data_dir).as_posix(),
        sha256=sha256_of(target),
        item_count=len(items),
        total_cents=sum(expense.amount_cents for expense in expenses),
        created_at=now(),
    )
    session.add(record)
    session.flush()
    return record


def delete_export(session: Session, settings: Settings, record: ExportRecord) -> None:
    """删除资料包文件与导出记录；文件已不存在时只删记录，并清理空的资料包目录。"""
    path = settings.data_dir / record.file_path
    path.unlink(missing_ok=True)
    parent = path.parent
    if parent != settings.packages_dir and parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()
    session.delete(record)
    session.flush()
