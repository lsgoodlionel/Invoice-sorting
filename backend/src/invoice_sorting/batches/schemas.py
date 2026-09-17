"""报销批次请求体校验。"""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from invoice_sorting.common.constants import ExportLayout

NAME_MAX = 100
SHORT_MAX = 50
EXTERNAL_NO_MAX = 100
NOTE_MAX = 2000
MAX_ITEMS_PER_REQUEST = 1000

_STRICT = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BatchCreate(BaseModel):
    model_config = _STRICT

    name: str = Field(min_length=1, max_length=NAME_MAX)
    project_id: int | None = None
    note: str = Field(default="", max_length=NOTE_MAX)


class BatchUpdate(BaseModel):
    model_config = _STRICT

    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX)
    project_id: int | None = None
    note: str | None = Field(default=None, max_length=NOTE_MAX)
    sent_via: str | None = Field(default=None, max_length=SHORT_MAX)
    receiver: str | None = Field(default=None, max_length=SHORT_MAX)
    external_no: str | None = Field(default=None, max_length=EXTERNAL_NO_MAX)

    @model_validator(mode="after")
    def _reject_null_name(self) -> "BatchUpdate":
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name 不能为空")
        return self

    def changes(self) -> dict[str, Any]:
        """只返回请求中出现的字段；文本字段传 null 视为清空。"""
        values = self.model_dump(include=self.model_fields_set)
        return {
            key: ("" if value is None and key != "project_id" else value)
            for key, value in values.items()
        }


class BatchItems(BaseModel):
    model_config = _STRICT

    add: list[int] = Field(default_factory=list, max_length=MAX_ITEMS_PER_REQUEST)
    remove: list[int] = Field(default_factory=list, max_length=MAX_ITEMS_PER_REQUEST)
    force: bool = False


class BatchSent(BaseModel):
    model_config = _STRICT

    sent_on: date
    sent_via: str = Field(default="", max_length=SHORT_MAX)
    receiver: str = Field(default="", max_length=SHORT_MAX)
    external_no: str = Field(default="", max_length=EXTERNAL_NO_MAX)


class BatchReceived(BaseModel):
    model_config = _STRICT

    received_on: date
    expense_ids: list[int] = Field(default_factory=list, max_length=MAX_ITEMS_PER_REQUEST)


class ExportRequest(BaseModel):
    model_config = _STRICT

    layout: ExportLayout = ExportLayout.BY_EXPENSE
