"""支出记录请求体校验。"""

from datetime import date
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from invoice_sorting.common.constants import ExpenseStatus

MERCHANT_MAX = 200
SUMMARY_MAX = 200
PAY_METHOD_MAX = 30
NOTE_MAX = 2000

DEFAULT_CURRENCY = "CNY"

Cents = Annotated[int, Field(ge=0, strict=True)]
Currency = Annotated[
    str,
    BeforeValidator(lambda value: value.strip().upper() if isinstance(value, str) else value),
    StringConstraints(pattern=r"^[A-Z]{3}$"),
]
NON_NULLABLE_FIELDS = (
    "spent_on",
    "amount_cents",
    "merchant",
    "summary",
    "pay_method",
    "is_online",
    "invoice_exempt",
    "currency",
)


class ExpenseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    spent_on: date
    amount_cents: Cents
    merchant: str = Field(min_length=1, max_length=MERCHANT_MAX)
    summary: str = Field(default="", max_length=SUMMARY_MAX)
    category_id: int | None = None
    project_id: int | None = None
    pay_method: str = Field(default="", max_length=PAY_METHOD_MAX)
    is_online: bool = False
    note: str = Field(default="", max_length=NOTE_MAX)
    invoice_exempt: bool = False
    currency: Currency = DEFAULT_CURRENCY
    original_amount_cents: Cents | None = None


class ExpenseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    spent_on: date | None = None
    amount_cents: Cents | None = None
    merchant: str | None = Field(default=None, min_length=1, max_length=MERCHANT_MAX)
    summary: str | None = Field(default=None, max_length=SUMMARY_MAX)
    category_id: int | None = None
    project_id: int | None = None
    pay_method: str | None = Field(default=None, max_length=PAY_METHOD_MAX)
    is_online: bool | None = None
    note: str | None = Field(default=None, max_length=NOTE_MAX)
    invoice_exempt: bool | None = None
    currency: Currency | None = None
    original_amount_cents: Cents | None = None

    @model_validator(mode="after")
    def _reject_null_required(self) -> "ExpenseUpdate":
        for name in NON_NULLABLE_FIELDS:
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} 不能为空")
        return self

    def changes(self) -> dict[str, Any]:
        values = self.model_dump(include=self.model_fields_set)
        if values.get("note") is None and "note" in values:
            values["note"] = ""
        return values


class StatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: ExpenseStatus | None
    note: str = Field(default="", max_length=NOTE_MAX)
