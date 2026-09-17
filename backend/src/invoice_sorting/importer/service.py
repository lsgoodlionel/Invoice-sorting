"""导入服务：逐个文件入库、解析发票或识别凭证、判重，最后按凭证组给出建议；单个文件失败不影响其他。"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.attachments import evidence_records
from invoice_sorting.attachments.file_keys import compute_file_key
from invoice_sorting.attachments.storage import (
    DuplicateFileError,
    absolute_path,
    guess_kind,
    relocate_attachment,
    store_file,
)
from invoice_sorting.checklist.regions import RegionPolicy
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.common.errors import AppError
from invoice_sorting.config import Settings
from invoice_sorting.db.models import Attachment, InvoiceData
from invoice_sorting.importer.groups import ImportGroup, build_groups
from invoice_sorting.importer.items import EvidenceItem, item_from_attachment
from invoice_sorting.importer.suggestions import (
    build_warnings,
    invoice_data_from,
    suggested_spent_on,
)
from invoice_sorting.parsers import ParsedInvoice, parse_invoice_file
from invoice_sorting.settings.service import buyer_identity, region_policy

logger = logging.getLogger(__name__)

DUPLICATE_FILE_REASON = "文件已导入"
UNRECOGNIZED_INVOICE_HINT = "无法识别发票内容，已作为附件导入"
UNEXPECTED_ERROR = "导入失败，请重试或手工添加"


@dataclass
class ImportResult:
    groups: list[ImportGroup] = field(default_factory=list)
    duplicates: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    notices: list[dict[str, str]] = field(default_factory=list)  # 已导入但需提醒
    failed: dict[int, str] = field(default_factory=dict)  # 输入序号 → 失败原因
    entries: list[tuple[Attachment, EvidenceItem]] = field(default_factory=list)
    warnings: dict[int, list[str]] = field(default_factory=dict)  # 附件 id → 发票提示

    @property
    def attachment_ids(self) -> list[int]:
        return [attachment.id for attachment, _item in self.entries]

    def add_error(self, name: str, message: str, index: int | None = None) -> None:
        self.errors.append({"original_name": name, "error": message})
        if index is not None:
            self.failed[index] = message

    def add_notice(self, name: str, message: str) -> None:
        self.notices.append({"original_name": name, "message": message})

    def add_duplicate(self, name: str, expense_id: int | None, reason: str) -> None:
        self.duplicates.append(
            {"original_name": name, "existing_expense_id": expense_id, "reason": reason}
        )


@dataclass(frozen=True)
class _Context:
    session: Session
    settings: Settings
    buyer: tuple[str, str]
    policy: RegionPolicy
    result: ImportResult


def discard_attachment(session: Session, settings: Settings, attachment: Attachment) -> None:
    """删除刚入库的附件记录与文件（用于判重后撤销，不进回收站）。"""
    path = absolute_path(settings, attachment)
    session.delete(attachment)
    session.flush()
    path.unlink(missing_ok=True)


def _existing_invoice(session: Session, invoice_no: str | None) -> InvoiceData | None:
    if not invoice_no:
        return None
    return session.scalar(select(InvoiceData).where(InvoiceData.invoice_no == invoice_no))


def _register_invoice(ctx: _Context, attachment: Attachment, parsed: ParsedInvoice) -> None:
    session, settings = ctx.session, ctx.settings
    existing = _existing_invoice(session, parsed.invoice_no)
    if existing is not None:
        discard_attachment(session, settings, attachment)
        reason = f"发票号码 {parsed.invoice_no} 已存在"
        ctx.result.add_duplicate(attachment.original_name, existing.attachment.expense_id, reason)
        return
    attachment.kind = str(AttachmentKind.INVOICE)
    attachment.invoice_data = invoice_data_from(parsed)
    session.flush()
    relocate_attachment(session, settings, attachment)
    warnings = build_warnings(parsed, attachment.invoice_data, ctx.buyer, ctx.policy)
    ctx.result.warnings[attachment.id] = warnings
    item = item_from_attachment(attachment, parsed=parsed, occurred_on=suggested_spent_on(parsed))
    ctx.result.entries.append((attachment, item))


def _register_evidence(ctx: _Context, attachment: Attachment, src: Path) -> None:
    name = attachment.original_name
    recognized = evidence_records.recognize_file(src, name)
    guessed = AttachmentKind(attachment.kind)
    attachment.kind = str(evidence_records.kind_for_evidence(recognized, name, guessed))
    evidence_records.apply_evidence(attachment, recognized)
    ctx.session.flush()
    relocate_attachment(ctx.session, ctx.settings, attachment)
    ctx.result.entries.append((attachment, item_from_attachment(attachment)))
    if attachment.kind == AttachmentKind.INVOICE:
        ctx.result.add_notice(name, UNRECOGNIZED_INVOICE_HINT)


def _store(ctx: _Context, index: int, src: Path, name: str) -> Attachment | None:
    try:
        attachment = store_file(ctx.session, ctx.settings, src, name, guess_kind(name))
    except DuplicateFileError as exc:
        ctx.result.add_duplicate(name, exc.existing.expense_id, DUPLICATE_FILE_REASON)
        return None
    except AppError as exc:
        ctx.result.add_error(name, exc.message, index)
        return None
    attachment.file_key = compute_file_key(name)
    return attachment


def _import_one(ctx: _Context, index: int, src: Path, name: str) -> None:
    attachment = _store(ctx, index, src, name)
    if attachment is None:
        return
    try:
        parsed = parse_invoice_file(src)
        if parsed is not None:
            _register_invoice(ctx, attachment, parsed)
        else:
            _register_evidence(ctx, attachment, src)
    except Exception:
        logger.exception("导入文件时出错：%s", name)
        discard_attachment(ctx.session, ctx.settings, attachment)
        ctx.result.entries = [entry for entry in ctx.result.entries if entry[0] is not attachment]
        ctx.result.warnings.pop(attachment.id, None)
        ctx.result.add_error(name, UNEXPECTED_ERROR, index)


def import_files(
    session: Session, settings: Settings, paths: list[tuple[Path, str]]
) -> ImportResult:
    """导入 (源文件路径, 原始文件名) 列表并分组；源文件不改动。调用方负责提交事务。"""
    ctx = _Context(
        session, settings, buyer_identity(session), region_policy(session), ImportResult()
    )
    for index, (src, name) in enumerate(paths):
        _import_one(ctx, index, src, name)
    result = ctx.result
    result.groups = build_groups(session, result.entries, result.warnings)
    return result
