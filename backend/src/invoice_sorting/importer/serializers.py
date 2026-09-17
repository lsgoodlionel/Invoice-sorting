"""导入结果的接口形状（docs/api-contract.md: ImportSession / ImportRow）。"""

from typing import Any

from invoice_sorting.attachments.serializers import iso_date, serialize_attachment
from invoice_sorting.checklist.regions import DEFAULT_POLICY, RegionPolicy
from invoice_sorting.db.models import Expense
from invoice_sorting.importer.service import ImportResult, ImportRow


def serialize_match(expense: Expense | None) -> dict[str, Any] | None:
    if expense is None:
        return None
    return {
        "expense_id": expense.id,
        "merchant": expense.merchant,
        "amount_cents": expense.amount_cents,
        "spent_on": iso_date(expense.spent_on),
    }


def serialize_row(
    row: ImportRow, buyer: tuple[str, str] | None, policy: RegionPolicy = DEFAULT_POLICY
) -> dict[str, Any]:
    suggestion = row.suggestion
    return {
        "row_id": row.row_id,
        "attachment": serialize_attachment(row.attachment, buyer, policy),
        "is_invoice": True,
        "suggested": {
            "spent_on": iso_date(suggestion.spent_on),
            "amount_cents": suggestion.amount_cents,
            "merchant": suggestion.merchant,
            "summary": suggestion.summary,
            "category_id": suggestion.category_id,
            "is_online": suggestion.is_online,
        },
        "match": serialize_match(row.match),
        "warnings": list(row.warnings),
    }


def serialize_import(
    session_id: str,
    result: ImportResult,
    buyer: tuple[str, str] | None,
    policy: RegionPolicy = DEFAULT_POLICY,
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "rows": [serialize_row(row, buyer, policy) for row in result.rows],
        "attachments": [serialize_attachment(item, buyer, policy) for item in result.attachments],
        "duplicates": list(result.duplicates),
        "errors": list(result.errors),
        "notices": list(result.notices),
    }
