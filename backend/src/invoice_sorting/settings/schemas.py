"""设置、分类、经费项目、清单规则的请求体校验。"""

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StrictBool

from invoice_sorting.common.constants import AttachmentKind, ChecklistLevel

NAME_MAX = 50
PROJECT_NAME_MAX = 100
COLOR_MAX = 20
TEXT_MAX = 2000
MAX_OVERDUE_DAYS = 3650
REGION_MAX = 20
MAX_PLATFORMS = 50

StrictCents = Annotated[int, Field(ge=0, strict=True)]
STRICT_FORBID = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AppSettingsUpdate(BaseModel):
    model_config = STRICT_FORBID

    buyer_name: str | None = Field(default=None, max_length=200)
    buyer_tax_id: str | None = Field(default=None, max_length=50)
    overdue_days: Annotated[int, Field(ge=1, le=MAX_OVERDUE_DAYS, strict=True)] | None = None
    local_region: str | None = Field(default=None, max_length=REGION_MAX)
    detail_platforms: list[Annotated[str, Field(max_length=NAME_MAX)]] | None = Field(
        default=None, max_length=MAX_PLATFORMS
    )


class CategoryCreate(BaseModel):
    model_config = STRICT_FORBID

    name: str = Field(min_length=1, max_length=NAME_MAX)
    color: str = Field(default="gray", min_length=1, max_length=COLOR_MAX)
    keywords: list[Annotated[str, Field(min_length=1, max_length=NAME_MAX)]] = []
    route_hint: str = Field(default="", max_length=TEXT_MAX)


class CategoryUpdate(BaseModel):
    model_config = STRICT_FORBID

    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX)
    color: str | None = Field(default=None, min_length=1, max_length=COLOR_MAX)
    keywords: list[Annotated[str, Field(min_length=1, max_length=NAME_MAX)]] | None = None
    route_hint: str | None = Field(default=None, max_length=TEXT_MAX)
    sort: int | None = None
    archived: bool | None = None


class ProjectCreate(BaseModel):
    model_config = STRICT_FORBID

    code: str = Field(default="", max_length=NAME_MAX)
    name: str = Field(min_length=1, max_length=PROJECT_NAME_MAX)
    owner: str = Field(default="", max_length=NAME_MAX)


class ProjectUpdate(BaseModel):
    model_config = STRICT_FORBID

    code: str | None = Field(default=None, max_length=NAME_MAX)
    name: str | None = Field(default=None, min_length=1, max_length=PROJECT_NAME_MAX)
    owner: str | None = Field(default=None, max_length=NAME_MAX)
    active: bool | None = None


class RuleCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_gte: StrictCents | None = None
    amount_lt: StrictCents | None = None
    is_online: StrictBool | None = None
    is_nonlocal: StrictBool | None = None
    detail_platform: StrictBool | None = None
    invoice_exempt: StrictBool | None = None

    def to_json(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class ChecklistRuleCreate(BaseModel):
    model_config = STRICT_FORBID

    category_id: int | None = None
    attachment_kind: AttachmentKind
    level: ChecklistLevel = ChecklistLevel.REQUIRED
    condition: RuleCondition = RuleCondition()
    hint: str = Field(default="", max_length=TEXT_MAX)


class ChecklistRuleUpdate(BaseModel):
    model_config = STRICT_FORBID

    category_id: int | None = None
    attachment_kind: AttachmentKind | None = None
    level: ChecklistLevel | None = None
    condition: RuleCondition | None = None
    hint: str | None = Field(default=None, max_length=TEXT_MAX)


def present_values(model: BaseModel, nullable: tuple[str, ...] = ()) -> dict[str, Any]:
    """只取请求中出现的字段；非 nullable 字段传 null 时忽略。"""
    values = {name: getattr(model, name) for name in model.model_fields_set}
    return {k: v for k, v in values.items() if v is not None or k in nullable}
