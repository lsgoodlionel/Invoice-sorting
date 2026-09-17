"""凭证清单 API：标记清单项“不需要”或恢复。"""

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from invoice_sorting.common.constants import ChecklistState
from invoice_sorting.common.errors import NotFoundError, ok
from invoice_sorting.db.models import ChecklistItem
from invoice_sorting.expenses.serializers import serialize_expense_detail
from invoice_sorting.expenses.service import get_expense_or_404, refresh_expense
from invoice_sorting.settings.deps import ConfigDep, SessionDep

router = APIRouter(prefix="/api", tags=["凭证清单"])

REASON_MAX_CHARS = 500


class ChecklistItemPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    state: Literal["not_needed", "missing"]
    reason: str = Field(default="", max_length=REASON_MAX_CHARS)


@router.patch("/checklist-items/{item_id}")
def patch_checklist_item(
    item_id: int, body: ChecklistItemPatch, session: SessionDep, config: ConfigDep
) -> dict[str, Any]:
    item = session.get(ChecklistItem, item_id)
    if item is None:
        raise NotFoundError("清单项")
    expense = get_expense_or_404(session, item.expense_id)
    item.state = body.state
    item.reason = body.reason if body.state == ChecklistState.NOT_NEEDED else ""
    refresh_expense(session, config, expense)
    session.commit()
    return ok(serialize_expense_detail(session, expense))
