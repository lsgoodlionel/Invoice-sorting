"""上传文件：流式写入临时文件（带大小上限），再入库；失败时清理已复制的文件。"""

import tempfile
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from invoice_sorting.attachments.storage import absolute_path, guess_kind, store_file
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.common.errors import AppError
from invoice_sorting.config import MAX_UPLOAD_BYTES, Settings
from invoice_sorting.db.models import Attachment, Expense

CHUNK_BYTES = 1024 * 1024
UNNAMED_FILE = "未命名文件"


def upload_name(upload: UploadFile) -> str:
    return Path(upload.filename or "").name or UNNAMED_FILE


def save_upload(upload: UploadFile, target: Path) -> Path:
    """写入临时文件；超过上限立即中止，避免占满磁盘。"""
    written = 0
    with target.open("wb") as handle:
        while chunk := upload.file.read(CHUNK_BYTES):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                limit_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
                raise AppError(f"文件超过 {limit_mb}MB 上限：{upload_name(upload)}")
            handle.write(chunk)
    return target


def store_uploads(
    session: Session,
    settings: Settings,
    uploads: list[UploadFile],
    kind: AttachmentKind | None,
    expense: Expense | None,
) -> list[Attachment]:
    """逐个入库；任一失败时删除本次已复制进文件库的文件并抛出原错误。"""
    stored: list[Attachment] = []
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=settings.data_dir, prefix=".upload-") as tmp:
        try:
            for index, upload in enumerate(uploads):
                name = upload_name(upload)
                src = save_upload(upload, Path(tmp) / f"{index}.part")
                file_kind = kind or guess_kind(name)
                stored.append(store_file(session, settings, src, name, file_kind, expense))
        except Exception:
            for attachment in stored:
                absolute_path(settings, attachment).unlink(missing_ok=True)
            raise
    return stored
