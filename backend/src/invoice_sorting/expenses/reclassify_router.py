"""按最新规则重新分类（仅管理员）。"""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from invoice_sorting.attachments.serializers import iso_date
from invoice_sorting.auth.deps import ADMIN_ONLY
from invoice_sorting.common.errors import ok
from invoice_sorting.expenses.reclassify import (
    ReclassifySuggestion,
    apply_reclassify,
    preview_reclassify,
)
from invoice_sorting.settings.deps import ConfigDep, SessionDep

router = APIRouter(prefix="/api/reclassify", tags=["重新分类"], dependencies=ADMIN_ONLY)

MAX_CHANGES = 1000


class ReclassifyChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expense_id: int = Field(ge=1)
    category_id: int = Field(ge=1)


class ReclassifyApply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    changes: list[ReclassifyChange] = Field(min_length=1, max_length=MAX_CHANGES)


def _serialize(suggestion: ReclassifySuggestion) -> dict[str, Any]:
    expense = suggestion.expense
    return {
        "expense_id": expense.id,
        "spent_on": iso_date(expense.spent_on),
        "merchant": expense.merchant,
        "summary": expense.summary,
        "amount_cents": expense.amount_cents,
        "status": expense.status,
        "current_category_id": expense.category_id,
        "current_category_name": expense.category.name if expense.category else "",
        "suggested_category_id": suggestion.suggested_category.id,
        "suggested_category_name": suggestion.suggested_category.name,
        "basis": suggestion.basis,
    }


@router.get("/preview")
def get_preview(session: SessionDep, include_sent: bool = False) -> dict[str, Any]:
    return ok([_serialize(item) for item in preview_reclassify(session, include_sent)])


@router.post("/apply")
def post_apply(body: ReclassifyApply, session: SessionDep, config: ConfigDep) -> dict[str, Any]:
    changes = [(change.expense_id, change.category_id) for change in body.changes]
    updated = apply_reclassify(session, config, changes)
    session.commit()
    return ok({"updated": updated})
