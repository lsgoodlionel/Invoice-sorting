"""附件 API 请求体。"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from invoice_sorting.common.constants import AttachmentKind

MAX_BULK_IDS = 500

AttachmentIds = Annotated[
    list[Annotated[int, Field(gt=0)]], Field(min_length=1, max_length=MAX_BULK_IDS)
]


class AttachmentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: AttachmentKind | None = None
    expense_id: int | None = None


class BulkIds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: AttachmentIds


class BulkAssign(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: AttachmentIds
    expense_id: int | None
    kind: AttachmentKind | None = None
