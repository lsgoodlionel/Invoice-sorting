"""邀请码请求体。"""

from datetime import date

from pydantic import BaseModel, Field, StrictStr

from invoice_sorting.auth.schemas import NewPassword
from invoice_sorting.users.repository import UserRole
from invoice_sorting.users.schemas import DisplayName, Username

CODE_MAX = 64


class InviteCreate(BaseModel):
    role: UserRole = UserRole.MEMBER
    expires_on: date | None = None


class JoinBody(BaseModel):
    code: StrictStr = Field(max_length=CODE_MAX)
    username: Username
    password: NewPassword
    display_name: DisplayName | None = None
