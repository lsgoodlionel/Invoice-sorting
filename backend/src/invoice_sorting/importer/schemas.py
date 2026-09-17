"""导入确认请求体。"""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from invoice_sorting.expenses.schemas import MERCHANT_MAX, SUMMARY_MAX

ConfirmAction = Literal["create", "attach", "skip"]


class ConfirmRow(BaseModel):
    # 前端可能原样回传建议行中的其他字段，这里忽略未知字段
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    row_id: str = Field(min_length=1)
    action: ConfirmAction
    expense_id: int | None = None
    spent_on: date | None = None
    amount_cents: Annotated[int, Field(ge=0, strict=True)] | None = None
    merchant: str | None = Field(default="", max_length=MERCHANT_MAX)
    summary: str | None = Field(default="", max_length=SUMMARY_MAX)
    category_id: int | None = None
    project_id: int | None = None
    is_online: bool | None = None


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[ConfirmRow] = Field(min_length=1)
