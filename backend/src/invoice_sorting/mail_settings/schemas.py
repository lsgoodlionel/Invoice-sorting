"""邮件设置请求体：全部在系统边界校验。

`password`：缺省或 null 表示不修改；空字符串表示清除；其他值为新密码（加密后入库）。
"""

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, StrictInt, StrictStr

from invoice_sorting.mail_settings.constants import (
    BASE_URL_MAX,
    HOST_MAX,
    PASSWORD_MAX,
    SENDER_MAX,
    USERNAME_MAX,
)
from invoice_sorting.mail_settings.validation import (
    check_base_url,
    check_host,
    check_port,
    check_sender,
    text_field,
)
from invoice_sorting.signup.schemas import Email

Host = Annotated[
    StrictStr, AfterValidator(text_field("SMTP 服务器", HOST_MAX)), AfterValidator(check_host)
]
Port = Annotated[StrictInt, AfterValidator(check_port)]
SmtpUser = Annotated[StrictStr, AfterValidator(text_field("账号", USERNAME_MAX))]
Password = Annotated[StrictStr, Field(max_length=PASSWORD_MAX)]
Sender = Annotated[
    StrictStr, AfterValidator(text_field("发件人", SENDER_MAX)), AfterValidator(check_sender)
]
BaseUrl = Annotated[
    StrictStr, AfterValidator(text_field("站点地址", BASE_URL_MAX)), AfterValidator(check_base_url)
]


class MailSettingsPatch(BaseModel):
    host: Host | None = None
    port: Port | None = None
    tls: Literal["ssl", "starttls", "none"] | None = None
    username: SmtpUser | None = None
    password: Password | None = None
    sender: Sender | None = None
    public_base_url: BaseUrl | None = None


class TestEmailBody(BaseModel):
    to: Email
