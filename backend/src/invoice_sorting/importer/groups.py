"""凭证组：分组 → 摘要 → 与已有记录匹配 → 重复提示 → 建议操作（导入确认表与自动确认共用）。"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from invoice_sorting.db.models import Attachment
from invoice_sorting.importer.duplicates import duplicate_warnings, has_duplicate_warning
from invoice_sorting.importer.group_summary import GroupSummary, build_summary
from invoice_sorting.importer.grouping import ItemGroup, group_items
from invoice_sorting.importer.items import EvidenceItem
from invoice_sorting.importer.matching import MatchCandidate, find_candidates

ACTION_CREATE = "create"
ACTION_ATTACH = "attach"
ACTION_SKIP = "skip"


@dataclass(frozen=True)
class ImportGroup:
    group_id: str
    attachments: tuple[Attachment, ...]
    items: tuple[EvidenceItem, ...]
    link_reasons: tuple[str, ...]
    summary: GroupSummary
    match: MatchCandidate | None
    candidates: tuple[MatchCandidate, ...]
    suggested_action: str
    warnings: tuple[str, ...]

    @property
    def has_invoice(self) -> bool:
        return any(item.is_invoice for item in self.items)


def suggest_action(
    summary: GroupSummary, match: MatchCandidate | None, warnings: Sequence[str], has_invoice: bool
) -> str:
    """可能重复 → 跳过；强匹配 → 挂上；有金额和日期（或含发票待补填）→ 新建；否则留待归属。"""
    if has_duplicate_warning(warnings):
        return ACTION_SKIP
    if match is not None:
        return ACTION_ATTACH
    if has_invoice or (summary.amount_cents is not None and summary.spent_on is not None):
        return ACTION_CREATE
    return ACTION_SKIP


def build_group(
    session: Session,
    item_group: ItemGroup,
    attachments: Mapping[int, Attachment],
    extra_warnings: Mapping[int, Sequence[str]] | None = None,
) -> ImportGroup:
    items = item_group.items
    extra = extra_warnings or {}
    summary = build_summary(session, items)
    match, candidates = find_candidates(session, items)
    warnings = [warning for item in items for warning in extra.get(item.attachment_id, ())]
    warnings.extend(duplicate_warnings(session, items))
    unique_warnings = tuple(dict.fromkeys(warnings))
    has_invoice = any(item.is_invoice for item in items)
    return ImportGroup(
        group_id=uuid.uuid4().hex,
        attachments=tuple(attachments[item.attachment_id] for item in items),
        items=items,
        link_reasons=item_group.link_reasons,
        summary=summary,
        match=match,
        candidates=tuple(candidates),
        suggested_action=suggest_action(summary, match, unique_warnings, has_invoice),
        warnings=unique_warnings,
    )


def build_groups(
    session: Session,
    entries: Sequence[tuple[Attachment, EvidenceItem]],
    extra_warnings: Mapping[int, Sequence[str]] | None = None,
) -> list[ImportGroup]:
    attachments = {attachment.id: attachment for attachment, _item in entries}
    item_groups = group_items([item for _attachment, item in entries])
    return [build_group(session, group, attachments, extra_warnings) for group in item_groups]
