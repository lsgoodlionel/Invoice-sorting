"""导入结果的接口形状（docs/api-contract.md: ImportSession / ImportGroup / MatchCandidate）。"""

from typing import Any

from invoice_sorting.attachments.serializers import iso_date, serialize_attachment
from invoice_sorting.checklist.regions import DEFAULT_POLICY, RegionPolicy
from invoice_sorting.importer.group_summary import GroupSummary
from invoice_sorting.importer.groups import ImportGroup
from invoice_sorting.importer.scoring import MatchCandidate, missing_kinds
from invoice_sorting.importer.service import ImportResult


def serialize_candidate(candidate: MatchCandidate | None) -> dict[str, Any] | None:
    if candidate is None:
        return None
    expense = candidate.expense
    return {
        "expense_id": expense.id,
        "spent_on": iso_date(expense.spent_on),
        "merchant": expense.merchant,
        "amount_cents": expense.amount_cents,
        "currency": expense.currency or "CNY",
        "original_amount_cents": expense.original_amount_cents,
        "status": expense.status,
        "missing_kinds": missing_kinds(expense),
        "score": candidate.score,
        "reasons": list(candidate.reasons),
    }


def serialize_summary(summary: GroupSummary) -> dict[str, Any]:
    return {
        "spent_on": iso_date(summary.spent_on),
        "amount_cents": summary.amount_cents,
        "currency": summary.currency,
        "original_amount_cents": summary.original_amount_cents,
        "merchant": summary.merchant,
        "summary": summary.summary,
        "category_id": summary.category_id,
        "is_online": summary.is_online,
        "invoice_exempt": summary.invoice_exempt,
    }


def serialize_group(
    group: ImportGroup, buyer: tuple[str, str] | None, policy: RegionPolicy = DEFAULT_POLICY
) -> dict[str, Any]:
    return {
        "group_id": group.group_id,
        "attachments": [serialize_attachment(item, buyer, policy) for item in group.attachments],
        "link_reasons": list(group.link_reasons),
        "summary": serialize_summary(group.summary),
        "match": serialize_candidate(group.match),
        "candidates": [serialize_candidate(candidate) for candidate in group.candidates],
        "suggested_action": group.suggested_action,
        "warnings": list(group.warnings),
    }


def serialize_import(
    session_id: str,
    result: ImportResult,
    buyer: tuple[str, str] | None,
    policy: RegionPolicy = DEFAULT_POLICY,
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "groups": [serialize_group(group, buyer, policy) for group in result.groups],
        "duplicates": list(result.duplicates),
        "errors": list(result.errors),
        "notices": list(result.notices),
    }
