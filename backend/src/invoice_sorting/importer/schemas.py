"""导入确认请求体（docs/api-contract.md: ConfirmGroup）。"""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.expenses.schemas import MERCHANT_MAX, SUMMARY_MAX, Cents, Currency

ConfirmAction = Literal["create", "attach", "skip"]
MAX_GROUP_FILES = 200


class ConfirmGroup(BaseModel):
    # 前端可能原样回传组中的其他字段（attachments、summary 等），这里忽略未知字段
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    group_id: str = Field(min_length=1, max_length=100)
    attachment_ids: list[Annotated[int, Field(gt=0)]] = Field(
        min_length=1, max_length=MAX_GROUP_FILES
    )
    kinds: dict[str, AttachmentKind] = Field(default_factory=dict)
    action: ConfirmAction
    expense_id: int | None = None
    spent_on: date | None = None
    amount_cents: Cents | None = None
    currency: Currency | None = None
    original_amount_cents: Cents | None = None
    merchant: str | None = Field(default="", max_length=MERCHANT_MAX)
    summary: str | None = Field(default="", max_length=SUMMARY_MAX)
    category_id: int | None = None
    project_id: int | None = None
    is_online: bool | None = None
    invoice_exempt: bool | None = None


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    groups: list[ConfirmGroup] = Field(min_length=1)
