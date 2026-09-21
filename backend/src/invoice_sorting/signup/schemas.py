"""注册申请与推荐的请求体：全部在系统边界校验长度与格式。

`website` 是隐藏诱饵字段：正常用户看不到也不会填，填了即按机器人静默丢弃（不提示）。
"""

from datetime import date
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, StrictBool, StrictInt, StrictStr
from pydantic_core import PydanticCustomError

from invoice_sorting.auth.schemas import NewPassword
from invoice_sorting.platform_admin.schemas import PlanCode, Slug, TenantName
from invoice_sorting.signup.codes import is_valid_email, normalize_email
from invoice_sorting.signup.constants import (
    CODE_VALID_DAYS_MAX,
    CODE_VALID_DAYS_MIN,
    EMAIL_MAX,
    HONEYPOT_MAX,
    IDENTITY_MAX,
    LEDGER_NAME_MAX,
    MSG_EMAIL_FORMAT,
    NAME_MAX,
    NEEDS_MAX,
    REASON_MAX,
    REFERRAL_CODE_MAX,
    REFERRAL_QUOTA_MAX,
    REGISTER_CODE_MAX,
)
from invoice_sorting.users.schemas import DisplayName, Username


def _required(label: str, limit: int):  # noqa: ANN202 - 返回校验函数
    def check(value: str) -> str:
        text = value.strip()
        if not 1 <= len(text) <= limit:
            raise PydanticCustomError("text_length", f"{label}需为 1–{limit} 个字符")
        return text

    return check


def _check_email(value: str) -> str:
    email = normalize_email(value)
    if len(email) > EMAIL_MAX or not is_valid_email(email):
        raise PydanticCustomError("email_format", MSG_EMAIL_FORMAT)
    return email


def _strip(value: str) -> str:
    return value.strip()


Email = Annotated[StrictStr, AfterValidator(_check_email)]
ApplicantName = Annotated[StrictStr, AfterValidator(_required("姓名", NAME_MAX))]
Identity = Annotated[StrictStr, AfterValidator(_required("单位或身份", IDENTITY_MAX))]
Needs = Annotated[StrictStr, AfterValidator(_required("使用需求", NEEDS_MAX))]
LedgerName = Annotated[StrictStr, Field(max_length=LEDGER_NAME_MAX), AfterValidator(_strip)]
Reason = Annotated[StrictStr, Field(max_length=REASON_MAX), AfterValidator(_strip)]


class ApplyBody(BaseModel):
    name: ApplicantName
    email: Email
    identity: Identity
    needs: Needs
    ledger_name: LedgerName = ""
    ref: Annotated[StrictStr, Field(max_length=REFERRAL_CODE_MAX)] = ""
    website: Annotated[StrictStr, Field(max_length=HONEYPOT_MAX)] = ""  # 诱饵字段


class RegisterBody(BaseModel):
    code: Annotated[StrictStr, Field(min_length=1, max_length=REGISTER_CODE_MAX)]
    email: Email
    username: Username
    password: NewPassword
    display_name: DisplayName | None = None


class ApproveBody(BaseModel):
    """全部可选：不填则自动生成标识、用期望账本名、默认免费套餐、长期有效。"""

    slug: Slug | None = None
    name: TenantName | None = None
    plan_code: PlanCode | None = None
    expires_on: date | None = None


class RejectBody(BaseModel):
    reason: Reason = ""


class SignupSettingsPatch(BaseModel):
    require_approval: StrictBool | None = None
    monthly_referral_quota: Annotated[StrictInt, Field(ge=0, le=REFERRAL_QUOTA_MAX)] | None = None
    code_valid_days: (
        Annotated[StrictInt, Field(ge=CODE_VALID_DAYS_MIN, le=CODE_VALID_DAYS_MAX)] | None
    ) = None


class ReferrerPatch(BaseModel):
    is_disabled: StrictBool
