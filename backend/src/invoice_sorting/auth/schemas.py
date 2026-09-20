"""认证请求体。密码 8–128 个字符；登录/当前密码只限制上限，错误统一按“用户名或密码错误”处理。

用户名规则（3–32 位字母数字下划线点连字符）也定义在这里：首次设置初始密码时可能要填用户名，
用户管理与邀请等模块统一从 `users.schemas` 复用同一份规则。
"""

import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, StrictStr
from pydantic_core import PydanticCustomError

PASSWORD_MIN = 8
PASSWORD_MAX = 128
SUBMITTED_MAX = 1024
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]{3,32}$")
DEFAULT_ADMIN_USERNAME = "admin"

MSG_USERNAME_FORMAT = "用户名需为 3–32 个字符，只能包含字母、数字、下划线、点、连字符"


def _check_new_password(value: str) -> str:
    if not PASSWORD_MIN <= len(value) <= PASSWORD_MAX:
        raise PydanticCustomError(
            "password_length", f"密码长度需为 {PASSWORD_MIN}–{PASSWORD_MAX} 个字符"
        )
    return value


def _check_username(value: str) -> str:
    candidate = value.strip()
    if not USERNAME_PATTERN.fullmatch(candidate):
        raise PydanticCustomError("username_format", MSG_USERNAME_FORMAT)
    return candidate.lower()


NewPassword = Annotated[StrictStr, AfterValidator(_check_new_password)]
Username = Annotated[StrictStr, AfterValidator(_check_username)]
SubmittedText = Annotated[StrictStr, Field(max_length=SUBMITTED_MAX)]


class SetupBody(BaseModel):
    """首次设置初始密码。

    单账套部署只用 password（用户名固定为内置管理员 admin）；
    多账套部署首次启动时创建首个平台管理员，用户名由用户填写，默认 admin。
    """

    password: NewPassword
    username: Username = DEFAULT_ADMIN_USERNAME


class LoginBody(BaseModel):
    username: SubmittedText
    password: SubmittedText


class ChangePasswordBody(BaseModel):
    current_password: SubmittedText
    new_password: NewPassword
