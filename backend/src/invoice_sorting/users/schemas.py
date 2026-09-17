"""用户管理请求体：用户名 3–32 位字母数字下划线点连字符；姓名 1–32 个字符；密码 8–128。"""

import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, StrictStr
from pydantic_core import PydanticCustomError

from invoice_sorting.auth.schemas import NewPassword
from invoice_sorting.users.repository import UserRole

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]{3,32}$")
DISPLAY_NAME_MAX = 32


def _check_username(value: str) -> str:
    candidate = value.strip()
    if not USERNAME_PATTERN.fullmatch(candidate):
        raise PydanticCustomError(
            "username_format", "用户名需为 3–32 个字符，只能包含字母、数字、下划线、点、连字符"
        )
    return candidate.lower()


def _check_display_name(value: str) -> str:
    candidate = value.strip()
    if not 1 <= len(candidate) <= DISPLAY_NAME_MAX:
        raise PydanticCustomError("display_name_length", f"姓名需为 1–{DISPLAY_NAME_MAX} 个字符")
    return candidate


Username = Annotated[StrictStr, AfterValidator(_check_username)]
DisplayName = Annotated[StrictStr, AfterValidator(_check_display_name)]


class UserCreate(BaseModel):
    username: Username
    display_name: DisplayName | None = None
    password: NewPassword
    role: UserRole = UserRole.MEMBER


class UserUpdate(BaseModel):
    display_name: DisplayName | None = None
    role: UserRole | None = None
    is_active: bool | None = None


class PasswordReset(BaseModel):
    password: NewPassword
