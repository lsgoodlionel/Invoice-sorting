"""自动确认发票（收件箱与“待归属发票生成记录”共用）。

规则（蓝图 5.1）：有匹配的“已支出”记录 → 挂接；金额与日期都识别到 → 新建；否则跳过并说明原因。
每条在独立 SAVEPOINT 中确认，单条失败只回滚该条；调用方负责提交外层事务。
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from invoice_sorting.common.errors import AppError
from invoice_sorting.config import Settings
from invoice_sorting.db.models import Attachment
from invoice_sorting.db.session import ensure_transaction
from invoice_sorting.importer.confirm import confirm_rows
from invoice_sorting.importer.schemas import ConfirmRow
from invoice_sorting.importer.service import ImportRow
from invoice_sorting.importer.suggestions import Suggestion

logger = logging.getLogger(__name__)

UNKNOWN_MERCHANT = "未知商家"
MISSING_AMOUNT_REASON = "未识别到金额，请手工处理"
MISSING_DATE_REASON = "未识别到开票日期，请手工处理"
UNEXPECTED_REASON = "自动生成记录失败，请手工处理"


@dataclass
class AutoConfirmResult:
    created: list[int] = field(default_factory=list)
    attached: list[int] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)

    def skip(self, attachment_id: int, original_name: str, reason: str) -> None:
        self.skipped.append({"id": attachment_id, "original_name": original_name, "reason": reason})

    def as_dict(self) -> dict[str, Any]:
        return {
            "created": list(self.created),
            "attached": list(dict.fromkeys(self.attached)),
            "skipped": list(self.skipped),
        }


def auto_row(row: ImportRow) -> ConfirmRow | None:
    """有匹配 → 挂接；金额与日期都识别到 → 新建；否则返回 None（留在待归属）。"""
    suggestion = row.suggestion
    common = {
        "row_id": row.row_id,
        "spent_on": suggestion.spent_on,
        "amount_cents": suggestion.amount_cents,
        "merchant": suggestion.merchant or UNKNOWN_MERCHANT,
        "summary": suggestion.summary,
        "category_id": suggestion.category_id,
        "is_online": suggestion.is_online,
    }
    if row.match is not None:
        return ConfirmRow(action="attach", expense_id=row.match.id, **common)
    if suggestion.amount_cents is not None and suggestion.spent_on is not None:
        return ConfirmRow(action="create", **common)
    return None


def skip_reason(suggestion: Suggestion) -> str:
    if suggestion.amount_cents is None:
        return MISSING_AMOUNT_REASON
    return MISSING_DATE_REASON


def _confirm_in_savepoint(
    session: Session, settings: Settings, row: ImportRow, confirm: ConfirmRow
) -> dict[str, Any]:
    ensure_transaction(session)
    savepoint = session.begin_nested()
    try:
        outcome = confirm_rows(session, settings, {row.row_id: row.attachment.id}, [confirm])
    except Exception:
        savepoint.rollback()
        raise
    savepoint.commit()
    return outcome.as_dict()


def confirm_import_row(
    session: Session, settings: Settings, row: ImportRow, result: AutoConfirmResult
) -> None:
    """按自动规则确认一行，结果累加到 result；失败只记为跳过。"""
    attachment: Attachment = row.attachment
    attachment_id, name = attachment.id, attachment.original_name
    confirm = auto_row(row)
    if confirm is None:
        result.skip(attachment_id, name, skip_reason(row.suggestion))
        return
    try:
        outcome = _confirm_in_savepoint(session, settings, row, confirm)
    except AppError as exc:
        result.skip(attachment_id, name, exc.message)
        return
    except Exception:
        logger.exception("自动确认发票失败：%s", name)
        result.skip(attachment_id, name, UNEXPECTED_REASON)
        return
    result.created.extend(outcome["created"])
    result.attached.extend(outcome["attached"])


def auto_confirm_rows(
    session: Session, settings: Settings, rows: list[ImportRow]
) -> AutoConfirmResult:
    result = AutoConfirmResult()
    for row in rows:
        confirm_import_row(session, settings, row, result)
    return result
