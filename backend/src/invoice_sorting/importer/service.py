"""导入服务：逐个文件入库、解析发票或识别凭证、判重，最后按凭证组给出建议；单个文件失败不影响其他。

每个文件先做只读预检（类型、大小、重复）和识别（耗时的解析/OCR），再写数据库，
这样并发的分文件导入请求不会在识别期间长时间占用 SQLite 写锁。
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from invoice_sorting.attachments import evidence_records
from invoice_sorting.attachments.file_keys import compute_file_key
from invoice_sorting.attachments.filetypes import validate_file
from invoice_sorting.attachments.storage import (
    DuplicateFileError,
    absolute_path,
    guess_kind,
    relocate_attachment,
    sha256_of,
    store_file,
)
from invoice_sorting.checklist.regions import RegionPolicy
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.common.errors import AppError
from invoice_sorting.config import Settings
from invoice_sorting.db.models import Attachment, InvoiceData
from invoice_sorting.evidence import RecognizedEvidence
from invoice_sorting.importer.groups import ImportGroup, build_groups
from invoice_sorting.importer.items import EvidenceItem, item_from_attachment
from invoice_sorting.importer.recognition_labels import UNRECOGNIZED, recognized_as
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
STATUS_IMPORTED = "imported"
STATUS_DUPLICATE = "duplicate"
STATUS_ERROR = "error"


@dataclass(frozen=True)
class FileOutcome:
    """单个文件的导入结论（ImportFileResult 的内部形状）。"""

    original_name: str
    status: str
    attachment: Attachment | None = None
    item: EvidenceItem | None = None
    recognized_as: str = UNRECOGNIZED
    message: str = ""
    existing_expense_id: int | None = None
    warnings: tuple[str, ...] = ()  # 发票提示（购方不一致、外地发票等）


class ImportDatabaseError(Exception):
    """写库失败（如并发导入触发唯一约束）。调用方须回滚事务并删除 `paths` 中已复制的文件。"""

    def __init__(self, paths: tuple[Path, ...], is_duplicate: bool) -> None:
        super().__init__("导入写入数据库失败")
        self.paths = paths
        self.is_duplicate = is_duplicate


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

    def add_outcome(self, index: int, outcome: FileOutcome) -> None:
        name = outcome.original_name
        if outcome.status == STATUS_DUPLICATE:
            self.add_duplicate(name, outcome.existing_expense_id, outcome.message)
        elif outcome.status == STATUS_ERROR:
            self.add_error(name, outcome.message, index)
        elif outcome.attachment is not None and outcome.item is not None:
            self.entries.append((outcome.attachment, outcome.item))
            self.warnings[outcome.attachment.id] = list(outcome.warnings)
            if outcome.message:
                self.add_notice(name, outcome.message)


@dataclass(frozen=True)
class _Context:
    session: Session
    settings: Settings
    buyer: tuple[str, str]
    policy: RegionPolicy


@dataclass(frozen=True)
class _Recognition:
    parsed: ParsedInvoice | None
    evidence: RecognizedEvidence | None


def _duplicate(name: str, expense_id: int | None, reason: str) -> FileOutcome:
    return FileOutcome(name, STATUS_DUPLICATE, message=reason, existing_expense_id=expense_id)


def _error(name: str, message: str) -> FileOutcome:
    return FileOutcome(name, STATUS_ERROR, message=message)


def _imported(attachment: Attachment, item: EvidenceItem, **fields: Any) -> FileOutcome:
    return FileOutcome(
        attachment.original_name,
        STATUS_IMPORTED,
        attachment=attachment,
        item=item,
        recognized_as=recognized_as(attachment),
        **fields,
    )


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


def _register_invoice(ctx: _Context, attachment: Attachment, parsed: ParsedInvoice) -> FileOutcome:
    session, settings = ctx.session, ctx.settings
    existing = _existing_invoice(session, parsed.invoice_no)
    if existing is not None:
        name, expense_id = attachment.original_name, existing.attachment.expense_id
        discard_attachment(session, settings, attachment)
        return _duplicate(name, expense_id, f"发票号码 {parsed.invoice_no} 已存在")
    attachment.kind = str(AttachmentKind.INVOICE)
    attachment.invoice_data = invoice_data_from(parsed)
    session.flush()
    relocate_attachment(session, settings, attachment)
    warnings = build_warnings(parsed, attachment.invoice_data, ctx.buyer, ctx.policy)
    item = item_from_attachment(attachment, parsed=parsed, occurred_on=suggested_spent_on(parsed))
    return _imported(attachment, item, warnings=tuple(warnings))


def _register_evidence(
    ctx: _Context, attachment: Attachment, recognized: RecognizedEvidence
) -> FileOutcome:
    name = attachment.original_name
    guessed = AttachmentKind(attachment.kind)
    attachment.kind = str(evidence_records.kind_for_evidence(recognized, name, guessed))
    evidence_records.apply_evidence(attachment, recognized)
    ctx.session.flush()
    relocate_attachment(ctx.session, ctx.settings, attachment)
    is_invoice = attachment.kind == AttachmentKind.INVOICE
    message = UNRECOGNIZED_INVOICE_HINT if is_invoice else ""
    return _imported(attachment, item_from_attachment(attachment), message=message)


def _precheck(ctx: _Context, src: Path, name: str) -> FileOutcome | None:
    """只读校验：类型/大小不合规或文件已导入时直接给出结论。"""
    try:
        validate_file(src, name)
    except AppError as exc:
        return _error(name, exc.message)
    digest = sha256_of(src)
    existing = ctx.session.scalar(select(Attachment).where(Attachment.sha256 == digest))
    if existing is not None:
        return _duplicate(name, existing.expense_id, DUPLICATE_FILE_REASON)
    return None


def _recognize(src: Path, name: str) -> _Recognition:
    parsed = parse_invoice_file(src)
    if parsed is not None:
        return _Recognition(parsed, None)
    return _Recognition(None, evidence_records.recognize_file(src, name))


def _register(ctx: _Context, attachment: Attachment, recognition: _Recognition) -> FileOutcome:
    try:
        if recognition.parsed is not None:
            return _register_invoice(ctx, attachment, recognition.parsed)
        return _register_evidence(ctx, attachment, recognition.evidence)
    except SQLAlchemyError as exc:
        paths = (absolute_path(ctx.settings, attachment),)
        raise ImportDatabaseError(paths, isinstance(exc, IntegrityError)) from exc
    except Exception:
        logger.exception("导入文件时出错：%s", attachment.original_name)
        name = attachment.original_name
        discard_attachment(ctx.session, ctx.settings, attachment)
        return _error(name, UNEXPECTED_ERROR)


def _store_and_register(
    ctx: _Context, src: Path, name: str, recognition: _Recognition
) -> FileOutcome:
    try:
        attachment = store_file(ctx.session, ctx.settings, src, name, guess_kind(name))
    except DuplicateFileError as exc:
        return _duplicate(name, exc.existing.expense_id, DUPLICATE_FILE_REASON)
    except AppError as exc:
        return _error(name, exc.message)
    except SQLAlchemyError as exc:
        raise ImportDatabaseError((), isinstance(exc, IntegrityError)) from exc
    attachment.file_key = compute_file_key(name)
    return _register(ctx, attachment, recognition)


def _import_one(ctx: _Context, src: Path, name: str) -> FileOutcome:
    rejected = _precheck(ctx, src, name)
    if rejected is not None:
        return rejected
    try:
        recognition = _recognize(src, name)
    except Exception:
        logger.exception("识别文件时出错：%s", name)
        return _error(name, UNEXPECTED_ERROR)
    return _store_and_register(ctx, src, name, recognition)


def _context(session: Session, settings: Settings) -> _Context:
    return _Context(session, settings, buyer_identity(session), region_policy(session))


def import_single_file(
    session: Session, settings: Settings, src: Path, original_name: str
) -> FileOutcome:
    """导入单个文件（不分组）；源文件不改动。调用方负责提交，写库失败抛 ImportDatabaseError。"""
    return _import_one(_context(session, settings), src, original_name)


def import_files(
    session: Session, settings: Settings, paths: list[tuple[Path, str]]
) -> ImportResult:
    """导入 (源文件路径, 原始文件名) 列表并分组；源文件不改动。调用方负责提交事务。"""
    ctx = _context(session, settings)
    result = ImportResult()
    for index, (src, name) in enumerate(paths):
        result.add_outcome(index, _import_one(ctx, src, name))
    result.groups = build_groups(session, result.entries, result.warnings)
    return result
