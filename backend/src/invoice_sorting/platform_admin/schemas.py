"""平台后台请求体。

所有字段都在系统边界做校验：slug 只允许小写字母数字与连字符（挡住路径穿越），
额度为非负整数，套餐代码与名称限长。PATCH 一律用 `model_fields_set` 判断
「客户端有没有传这个字段」，因此 `null` 表示清空（例如永久有效），不传表示不修改。
"""

from datetime import date
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, StrictBool, StrictInt, StrictStr

from invoice_sorting.auth.schemas import NewPassword
from invoice_sorting.control.repository import SLUG_PATTERN
from invoice_sorting.users.repository import UserRole
from invoice_sorting.users.schemas import DisplayName, Username

SLUG_MAX = 50
NAME_MAX = 100
PLAN_CODE_MAX = 30
PLAN_NAME_MAX = 50
NOTE_MAX = 200
CUSTOMER_MAX = 100
INSTANCE_MAX = 64
QUOTA_MAX = 1_000_000

Slug = Annotated[StrictStr, Field(min_length=1, max_length=SLUG_MAX, pattern=SLUG_PATTERN.pattern)]
TenantName = Annotated[StrictStr, Field(min_length=1, max_length=NAME_MAX)]
PlanCode = Annotated[StrictStr, Field(min_length=1, max_length=PLAN_CODE_MAX)]
PlanName = Annotated[StrictStr, Field(min_length=1, max_length=PLAN_NAME_MAX)]
CustomerName = Annotated[StrictStr, Field(min_length=1, max_length=CUSTOMER_MAX)]
Note = Annotated[StrictStr, Field(max_length=NOTE_MAX)]
Quota = Annotated[StrictInt, Field(ge=0, le=QUOTA_MAX)]


class TenantStatus(StrEnum):
    """账套状态：停用与关闭都会立刻释放该账套的数据库连接。"""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class LicenseStatusValue(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class TenantCreate(BaseModel):
    """开通账套：可同时开通首个管理员账号，或改为签发一张管理员邀请码。"""

    slug: Slug
    name: TenantName | None = None
    plan_code: PlanCode | None = None
    expires_on: date | None = None
    admin_username: Username | None = None
    admin_password: NewPassword | None = None
    admin_display_name: DisplayName | None = None
    with_invite: StrictBool = False


class TenantUpdate(BaseModel):
    name: TenantName | None = None
    plan_code: PlanCode | None = None
    expires_on: date | None = None
    status: TenantStatus | None = None


class PlanCreate(BaseModel):
    """额度为 0 表示不限制。"""

    code: PlanCode
    name: PlanName | None = None
    max_users: Quota = 0
    max_storage_mb: Quota = 0
    max_expenses_per_month: Quota = 0
    features: dict = Field(default_factory=dict)


class PlanUpdate(BaseModel):
    name: PlanName | None = None
    max_users: Quota | None = None
    max_storage_mb: Quota | None = None
    max_expenses_per_month: Quota | None = None
    features: dict | None = None


class MemberCreate(BaseModel):
    """新账号需要填初始密码；已存在的账号直接加入该账套，不改它的密码。"""

    username: Username
    display_name: DisplayName | None = None
    password: NewPassword | None = None
    role: UserRole = UserRole.MEMBER


class MemberUpdate(BaseModel):
    display_name: DisplayName | None = None
    role: UserRole | None = None
    is_active: StrictBool | None = None


class MemberPassword(BaseModel):
    password: NewPassword


class InviteCreate(BaseModel):
    role: UserRole = UserRole.MEMBER
    expires_on: date | None = None


class LicenseCreate(BaseModel):
    """签发授权记录；密钥由服务端用 secrets 生成，不接受客户端指定。"""

    customer_name: CustomerName
    max_users: Quota = 0
    valid_until: date | None = None
    note: Note = ""
    features: dict = Field(default_factory=dict)


class LicenseUpdate(BaseModel):
    customer_name: CustomerName | None = None
    max_users: Quota | None = None
    valid_until: date | None = None
    status: LicenseStatusValue | None = None
    note: Note | None = None
