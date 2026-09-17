"""分文件导入：单个文件入库并提交、记入会话，以及 finish 时从数据库重建凭证组。"""

import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from invoice_sorting.attachments.serializers import serialize_attachment
from invoice_sorting.attachments.storage import absolute_path
from invoice_sorting.checklist.regions import RegionPolicy
from invoice_sorting.config import Settings
from invoice_sorting.db.models import Attachment
from invoice_sorting.importer.groups import build_groups
from invoice_sorting.importer.items import EvidenceItem, item_from_attachment
from invoice_sorting.importer.service import (
    DUPLICATE_FILE_REASON,
    STATUS_DUPLICATE,
    STATUS_ERROR,
    STATUS_IMPORTED,
    UNEXPECTED_ERROR,
    FileOutcome,
    ImportDatabaseError,
    ImportResult,
    import_single_file,
)
from invoice_sorting.importer.sessions import ImportSessionStore, SessionSnapshot

logger = logging.getLogger(__name__)


def _unlink(paths: tuple[Path, ...]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.exception("清理导入失败的文件时出错：%s", path)


def _rolled_back(
    session: Session, name: str, paths: tuple[Path, ...], is_duplicate: bool
) -> FileOutcome:
    session.rollback()
    _unlink(paths)
    if is_duplicate:
        return FileOutcome(name, STATUS_DUPLICATE, message=DUPLICATE_FILE_REASON)
    return FileOutcome(name, STATUS_ERROR, message=UNEXPECTED_ERROR)


def import_and_commit(
    session: Session, settings: Settings, src: Path, original_name: str
) -> FileOutcome:
    """导入单个文件并提交。并发导入触发唯一约束时回滚本请求、删除已复制文件并判为重复。"""
    try:
        outcome = import_single_file(session, settings, src, original_name)
    except ImportDatabaseError as exc:
        logger.warning("导入写库冲突，已回滚：%s", original_name, exc_info=exc.__cause__)
        return _rolled_back(session, original_name, exc.paths, exc.is_duplicate)
    attachment = outcome.attachment
    paths = (absolute_path(settings, attachment),) if attachment is not None else ()
    try:
        session.commit()
    except SQLAlchemyError as exc:
        logger.warning("导入提交失败，已回滚：%s", original_name, exc_info=exc)
        return _rolled_back(session, original_name, paths, isinstance(exc, IntegrityError))
    return outcome


def record_outcome(store: ImportSessionStore, session_id: str, outcome: FileOutcome) -> None:
    """把单个文件的结论累计进会话（与一次性导入的 ImportSession 同形状）。"""
    name, message = outcome.original_name, outcome.message
    if outcome.status == STATUS_DUPLICATE:
        duplicate = {
            "original_name": name,
            "existing_expense_id": outcome.existing_expense_id,
            "reason": message,
        }
        store.add_file_outcome(session_id, duplicate=duplicate)
    elif outcome.status == STATUS_ERROR:
        store.add_file_outcome(session_id, error={"original_name": name, "error": message})
    elif outcome.attachment is not None:
        item = outcome.item
        store.add_file_outcome(
            session_id,
            attachment_id=outcome.attachment.id,
            warnings=outcome.warnings,
            occurred_on=item.occurred_on if item is not None and item.is_invoice else None,
            notice={"original_name": name, "message": message} if message else None,
        )


def serialize_file_outcome(
    outcome: FileOutcome, buyer: tuple[str, str] | None, policy: RegionPolicy
) -> dict[str, Any]:
    attachment = outcome.attachment
    is_imported = outcome.status == STATUS_IMPORTED and attachment is not None
    return {
        "original_name": outcome.original_name,
        "status": outcome.status,
        "attachment": serialize_attachment(attachment, buyer, policy) if is_imported else None,
        "recognized_as": outcome.recognized_as,
        "message": outcome.message,
        "existing_expense_id": outcome.existing_expense_id,
    }


def session_entries(
    session: Session, snapshot: SessionSnapshot
) -> list[tuple[Attachment, EvidenceItem]]:
    """会话内仍待归属的附件（已删除或已归属的跳过），按入库顺序重建凭证项。"""
    if not snapshot.attachment_ids:
        return []
    query = (
        select(Attachment)
        .where(Attachment.id.in_(snapshot.attachment_ids), Attachment.expense_id.is_(None))
        .order_by(Attachment.id)
    )
    return [
        (
            attachment,
            item_from_attachment(attachment, occurred_on=snapshot.occurred_on.get(attachment.id)),
        )
        for attachment in session.scalars(query)
    ]


def finish_session(session: Session, snapshot: SessionSnapshot) -> ImportResult:
    """对会话内全部已导入文件统一分组、匹配；duplicates/errors/notices 为会话累计。"""
    entries = session_entries(session, snapshot)
    return ImportResult(
        groups=build_groups(session, entries, snapshot.warnings),
        duplicates=[dict(record) for record in snapshot.duplicates],
        errors=[dict(record) for record in snapshot.errors],
        notices=[dict(record) for record in snapshot.notices],
        entries=entries,
    )
