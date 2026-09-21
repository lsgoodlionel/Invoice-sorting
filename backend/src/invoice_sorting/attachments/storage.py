"""文件库：附件入库、去重、命名、移动与回收站（蓝图 7.3 / 8.1）。

- `attachment.file_path` 为相对 `settings.data_dir` 的 POSIX 路径。
- `expense.folder_path` 为相对 `settings.library_dir` 的 POSIX 路径（见 db/models.py 注释）。
"""

import hashlib
import re
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.attachments.filetypes import extension_for, guess_kind, validate_file
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.common.errors import ConflictError
from invoice_sorting.common.money import cents_to_yuan
from invoice_sorting.config import Settings
from invoice_sorting.db.models import TZ, Attachment, Expense

__all__ = [
    "DuplicateFileError",
    "absolute_path",
    "assign_attachment",
    "attachment_file_name",
    "guess_kind",
    "new_file_destination",
    "sha256_of",
    "store_file",
    "sync_expense_folder",
    "trash_attachment",
    "trash_expense_files",
]

UNASSIGNED_DIRNAME = "待归属"
MERCHANT_MAX_CHARS = 30
HASH_CHUNK_BYTES = 1024 * 1024
ILLEGAL_PATH_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


class DuplicateFileError(ConflictError):
    """文件哈希与已有附件相同。`existing` 为已存在的附件。"""

    def __init__(self, existing: Attachment) -> None:
        where = f"记录 #{existing.expense_id}" if existing.expense_id else "待归属附件"
        super().__init__(f"文件已存在（{where}）")
        self.existing = existing


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def absolute_path(settings: Settings, attachment: Attachment) -> Path:
    return settings.data_dir / attachment.file_path


def safe_component(text: str) -> str:
    """把非法路径字符替换为 `_`，去掉首尾空白与点。"""
    return ILLEGAL_PATH_CHARS.sub("_", text).strip().strip(".")


def _relative_to_data(settings: Settings, path: Path) -> str:
    return path.relative_to(settings.data_dir).as_posix()


def _kind_label(kind: str) -> str:
    try:
        return AttachmentKind(kind).label
    except ValueError:
        return AttachmentKind.OTHER.label


def _sequence(attachment: Attachment) -> int:
    expense = attachment.expense
    if expense is None:
        return attachment.id or 0
    same_kind = sorted(
        item.id for item in expense.attachments if item.kind == attachment.kind and item.id
    )
    if attachment.id in same_kind:
        return same_kind.index(attachment.id) + 1
    return len(same_kind) + 1


def attachment_file_name(attachment: Attachment) -> str:
    """`{附件类型中文}_{发票号或序号}.{ext}`；待归属附件的序号使用附件 id。"""
    invoice = attachment.invoice_data
    invoice_no = safe_component(invoice.invoice_no) if invoice and invoice.invoice_no else ""
    token = invoice_no or str(_sequence(attachment))
    extension = extension_for(attachment.original_name, attachment.mime)
    return f"{_kind_label(attachment.kind)}_{token}{extension}"


def _free_path(directory: Path, filename: str, current: Path | None) -> Path:
    """返回目录下可用的文件/文件夹路径；与 current 相同视为可用，冲突时追加 `_2`、`_3`…"""
    candidate = directory / filename
    stem, suffix = Path(filename).stem, Path(filename).suffix
    index = 2
    while candidate.exists() and candidate != current:
        candidate = directory / f"{stem}_{index}{suffix}"
        index += 1
    return candidate


def _free_dir(parent: Path, name: str, current: Path | None) -> Path:
    candidate = parent / name
    index = 2
    while candidate.exists() and candidate != current:
        candidate = parent / f"{name}_{index}"
        index += 1
    return candidate


def _prune_empty_dirs(directory: Path, stop: Path) -> None:
    while directory != stop and stop in directory.parents:
        try:
            directory.rmdir()
        except OSError:
            return
        directory = directory.parent


def expense_folder_name(expense: Expense) -> str:
    merchant = safe_component(expense.merchant or "")[:MERCHANT_MAX_CHARS] or "未填商家"
    category = safe_component(expense.category.name) if expense.category else "未分类"
    amount = cents_to_yuan(expense.amount_cents)
    return f"{expense.spent_on:%Y%m%d}_{merchant}_{category}_{amount}_E{expense.id:04d}"


def _rebase_attachments(settings: Settings, expense: Expense, old: str, new: str) -> None:
    library = settings.library_dir.relative_to(settings.data_dir).as_posix()
    old_prefix, new_prefix = f"{library}/{old}/", f"{library}/{new}/"
    for attachment in expense.attachments:
        if attachment.file_path.startswith(old_prefix):
            attachment.file_path = new_prefix + attachment.file_path[len(old_prefix) :]


def sync_expense_folder(session: Session, settings: Settings, expense: Expense) -> None:
    """按当前字段计算文件夹名；变化时整体移动文件夹并更新附件路径。"""
    if expense.deleted:
        return
    if expense.id is None:
        session.flush()
    library = settings.library_dir
    parent = f"{expense.spent_on:%Y}/{expense.spent_on:%m}"
    current = expense.folder_path
    current_dir = library / current if current else None
    target = _free_dir(library / parent, expense_folder_name(expense), current_dir)
    new_rel = target.relative_to(library).as_posix()
    if new_rel == current:
        target.mkdir(parents=True, exist_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if current_dir is not None and current_dir.is_dir():
        shutil.move(current_dir, target)
        _prune_empty_dirs(current_dir.parent, library)
        _rebase_attachments(settings, expense, current, new_rel)
    else:
        target.mkdir(parents=True, exist_ok=True)
    expense.folder_path = new_rel


def _target_dir(session: Session, settings: Settings, expense: Expense | None) -> Path:
    if expense is None:
        return settings.library_dir / UNASSIGNED_DIRNAME
    if not expense.folder_path or not (settings.library_dir / expense.folder_path).is_dir():
        sync_expense_folder(session, settings, expense)
    return settings.library_dir / expense.folder_path


def new_file_destination(session: Session, settings: Settings, attachment: Attachment) -> Path:
    """按归属与命名规则为一个已 flush 的新附件选定空闲的落盘路径（目录已建好，文件未写）。"""
    directory = _target_dir(session, settings, attachment.expense)
    directory.mkdir(parents=True, exist_ok=True)
    return _free_path(directory, attachment_file_name(attachment), None)


def store_file(
    session: Session,
    settings: Settings,
    src: Path,
    original_name: str,
    kind: AttachmentKind = AttachmentKind.OTHER,
    expense: Expense | None = None,
) -> Attachment:
    """校验并复制文件入库（原文件不改动）。重复文件抛 DuplicateFileError。"""
    mime, size = validate_file(src, original_name)
    digest = sha256_of(src)
    existing = session.scalar(select(Attachment).where(Attachment.sha256 == digest))
    if existing is not None:
        raise DuplicateFileError(existing)
    attachment = Attachment(
        kind=str(kind),
        original_name=original_name,
        sha256=digest,
        mime=mime,
        size=size,
        file_path="",
        expense=expense,
    )
    session.add(attachment)
    session.flush()
    destination = new_file_destination(session, settings, attachment)
    shutil.copyfile(src, destination)
    attachment.file_path = _relative_to_data(settings, destination)
    session.flush()
    return attachment


def relocate_attachment(session: Session, settings: Settings, attachment: Attachment) -> None:
    """按当前归属与命名规则移动/重命名附件文件（如类型或发票号变化后）。"""
    directory = _target_dir(session, settings, attachment.expense)
    directory.mkdir(parents=True, exist_ok=True)
    current = absolute_path(settings, attachment)
    destination = _free_path(directory, attachment_file_name(attachment), current)
    if destination != current and current.is_file():
        shutil.move(current, destination)
        attachment.file_path = _relative_to_data(settings, destination)
    session.flush()


def assign_attachment(
    session: Session, settings: Settings, attachment: Attachment, expense: Expense | None
) -> Attachment:
    """把附件挂到支出（移动到其文件夹），或 expense=None 移回待归属。"""
    attachment.expense = expense
    session.flush()
    relocate_attachment(session, settings, attachment)
    return attachment


def trash_attachment(session: Session, settings: Settings, attachment: Attachment) -> None:
    """文件移入回收站，删除附件记录（含 invoice_data）。"""
    source = absolute_path(settings, attachment)
    settings.trash_dir.mkdir(parents=True, exist_ok=True)
    name = f"A{attachment.id:06d}_{source.name}"
    if source.is_file():
        shutil.move(source, _free_path(settings.trash_dir, name, None))
    if attachment.expense is not None:
        attachment.expense.attachments.remove(attachment)
    session.delete(attachment)
    session.flush()


def trash_expense_files(session: Session, settings: Settings, expense: Expense) -> None:
    """软删除支出时：附件文件移入回收站子目录，记录保留并指向新位置。"""
    stamp = datetime.now(TZ).strftime("%Y%m%d%H%M%S")
    trash_dir = _free_dir(settings.trash_dir, f"E{expense.id:04d}_{stamp}", None)
    trash_dir.mkdir(parents=True, exist_ok=True)
    for attachment in expense.attachments:
        source = absolute_path(settings, attachment)
        if not source.is_file():
            continue
        destination = _free_path(trash_dir, source.name, None)
        shutil.move(source, destination)
        attachment.file_path = _relative_to_data(settings, destination)
    if expense.folder_path:
        _prune_empty_dirs(settings.library_dir / expense.folder_path, settings.library_dir)
        expense.folder_path = ""
    session.flush()
