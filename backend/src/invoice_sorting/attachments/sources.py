"""复合凭证原始来源文件的存储与判重。"""

import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.attachments.storage import sha256_of
from invoice_sorting.config import Settings
from invoice_sorting.db.models import SourceDocument

SOURCE_DIR = "导入来源"


class DuplicateSourceError(Exception):
    def __init__(self, existing: SourceDocument) -> None:
        super().__init__("来源文件已导入")
        self.existing = existing


def source_absolute_path(settings: Settings, source: SourceDocument) -> Path:
    return settings.data_dir / source.file_path


def store_source_document(
    session: Session, settings: Settings, src: Path, original_name: str
) -> SourceDocument:
    digest = sha256_of(src)
    existing = session.scalar(select(SourceDocument).where(SourceDocument.sha256 == digest))
    if existing is not None:
        raise DuplicateSourceError(existing)
    destination = settings.data_dir / SOURCE_DIR / f"{digest}{src.suffix.lower()}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, destination)
    source = SourceDocument(
        sha256=digest,
        file_path=destination.relative_to(settings.data_dir).as_posix(),
        original_name=original_name,
        mime="application/pdf",
        size=destination.stat().st_size,
    )
    session.add(source)
    try:
        session.flush()
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return source
