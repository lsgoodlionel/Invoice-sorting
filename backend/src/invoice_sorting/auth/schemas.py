"""认证请求体。密码 8–128 个字符；登录/当前密码只限制上限，错误统一按“用户名或密码错误”处理。"""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, StrictStr
from pydantic_core import PydanticCustomError

PASSWORD_MIN = 8
PASSWORD_MAX = 128
SUBMITTED_MAX = 1024


def _check_new_password(value: str) -> str:
    if not PASSWORD_MIN <= len(value) <= PASSWORD_MAX:
        raise PydanticCustomError(
            "password_length", f"密码长度需为 {PASSWORD_MIN}–{PASSWORD_MAX} 个字符"
        )
    return value


NewPassword = Annotated[StrictStr, AfterValidator(_check_new_password)]
SubmittedText = Annotated[StrictStr, Field(max_length=SUBMITTED_MAX)]


class SetupBody(BaseModel):
    password: NewPassword


class LoginBody(BaseModel):
    username: SubmittedText
    password: SubmittedText


class ChangePasswordBody(BaseModel):
    current_password: SubmittedText
    new_password: NewPassword
