"""按凭证组自动确认（收件箱与待归属“生成记录”共用，设计 5.3）。

强匹配 → 挂上；无匹配且有金额和日期 → 新建；可能重复或缺金额/日期 → 留在待归属并说明原因。
每组处理前重新匹配（前一组可能刚建或挂了记录），并在独立 SAVEPOINT 中确认，单组失败只回滚该组；
调用方负责提交外层事务。
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from invoice_sorting.common.errors import AppError
from invoice_sorting.config import Settings
from invoice_sorting.db.models import Attachment
from invoice_sorting.db.session import ensure_transaction
from invoice_sorting.importer.confirm import confirm_groups
from invoice_sorting.importer.duplicates import DUPLICATE_PREFIX
from invoice_sorting.importer.grouping import ItemGroup, group_items
from invoice_sorting.importer.groups import ImportGroup, build_group
from invoice_sorting.importer.items import EvidenceItem
from invoice_sorting.importer.schemas import ConfirmGroup

logger = logging.getLogger(__name__)

UNKNOWN_MERCHANT = "未知商家"
MISSING_AMOUNT_REASON = "未识别到金额，请手工处理"
MISSING_DATE_REASON = "未识别到开票日期，请手工处理"
MISSING_EVIDENCE_DATE_REASON = "未识别到日期，请手工处理"
NO_INVOICE_DATA_REASON = "未识别到发票内容，请先重新识别或手工处理"
UNEXPECTED_REASON = "自动生成记录失败，请手工处理"


@dataclass
class AutoConfirmResult:
    created: list[int] = field(default_factory=list)
    attached: list[int] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)

    def skip(self, attachment_id: int, original_name: str, reason: str) -> None:
        self.skipped.append({"id": attachment_id, "original_name": original_name, "reason": reason})

    def skip_all(self, attachments: Sequence[Attachment], reason: str) -> None:
        for attachment in attachments:
            self.skip(attachment.id, attachment.original_name, reason)

    def as_dict(self) -> dict[str, Any]:
        return {
            "created": list(self.created),
            "attached": list(dict.fromkeys(self.attached)),
            "skipped": list(self.skipped),
        }


def auto_confirm_request(group: ImportGroup) -> ConfirmGroup | None:
    """可自动确认时返回确认请求，否则返回 None（留在待归属）。"""
    summary = group.summary
    if any(warning.startswith(DUPLICATE_PREFIX) for warning in group.warnings):
        return None
    common = {
        "group_id": group.group_id,
        "attachment_ids": [attachment.id for attachment in group.attachments],
        "spent_on": summary.spent_on,
        "amount_cents": summary.amount_cents,
        "currency": summary.currency,
        "original_amount_cents": summary.original_amount_cents,
        "merchant": summary.merchant or UNKNOWN_MERCHANT,
        "summary": summary.summary,
        "category_id": summary.category_id,
        "is_online": summary.is_online,
        "invoice_exempt": summary.invoice_exempt,
    }
    if group.match is not None:
        return ConfirmGroup(action="attach", expense_id=group.match.expense.id, **common)
    if summary.amount_cents is not None and summary.spent_on is not None:
        return ConfirmGroup(action="create", **common)
    return None


def skip_reason(group: ImportGroup) -> str:
    duplicate = next((w for w in group.warnings if w.startswith(DUPLICATE_PREFIX)), None)
    if duplicate is not None:
        return duplicate
    if group.summary.amount_cents is None:
        lacks_invoice_data = group.has_invoice and not any(item.has_data for item in group.items)
        return NO_INVOICE_DATA_REASON if lacks_invoice_data else MISSING_AMOUNT_REASON
    return MISSING_DATE_REASON if group.has_invoice else MISSING_EVIDENCE_DATE_REASON


def _confirm_in_savepoint(
    session: Session, settings: Settings, confirm: ConfirmGroup
) -> dict[str, Any]:
    ensure_transaction(session)
    savepoint = session.begin_nested()
    try:
        outcome = confirm_groups(session, settings, None, [confirm])
    except Exception:
        savepoint.rollback()
        raise
    savepoint.commit()
    return outcome.as_dict()


def confirm_group_automatically(
    session: Session, settings: Settings, group: ImportGroup, result: AutoConfirmResult
) -> None:
    """按自动规则确认一组，结果累加到 result；失败只记为跳过。"""
    confirm = auto_confirm_request(group)
    if confirm is None:
        result.skip_all(group.attachments, skip_reason(group))
        return
    try:
        outcome = _confirm_in_savepoint(session, settings, confirm)
    except AppError as exc:
        result.skip_all(group.attachments, exc.message)
        return
    except Exception:
        logger.exception("自动确认凭证组失败：%s", [a.original_name for a in group.attachments])
        result.skip_all(group.attachments, UNEXPECTED_REASON)
        return
    result.created.extend(outcome["created"])
    result.attached.extend(outcome["attached"])


def _build(
    session: Session,
    item_group: ItemGroup,
    attachments: Mapping[int, Attachment],
    warnings: Mapping[int, Sequence[str]] | None,
) -> ImportGroup | None:
    try:
        session.flush()
        return build_group(session, item_group, attachments, warnings)
    except Exception:
        logger.exception("凭证组匹配失败：%s", [item.original_name for item in item_group.items])
        return None


def auto_confirm_entries(
    session: Session,
    settings: Settings,
    entries: Sequence[tuple[Attachment, EvidenceItem]],
    warnings: Mapping[int, Sequence[str]] | None = None,
) -> AutoConfirmResult:
    """先分组，再逐组重新匹配并确认。"""
    result = AutoConfirmResult()
    attachments = {attachment.id: attachment for attachment, _item in entries}
    for item_group in group_items([item for _attachment, item in entries]):
        group = _build(session, item_group, attachments, warnings)
        if group is None:
            members = [attachments[item.attachment_id] for item in item_group.items]
            result.skip_all(members, UNEXPECTED_REASON)
            continue
        confirm_group_automatically(session, settings, group, result)
    return result
