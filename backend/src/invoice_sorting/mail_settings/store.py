"""邮件设置单行表的读写：保存（密码加密）、记录最近一次验证结果。调用方负责提交。"""

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from invoice_sorting.common.errors import AppError
from invoice_sorting.common.secret_box import SecretUnavailableError, encrypt_secret
from invoice_sorting.config import Settings
from invoice_sorting.control.mail_models import MAIL_SETTINGS_ROW_ID, MailSettings
from invoice_sorting.db.models import now
from invoice_sorting.mailer.errors import ErrorInfo

logger = logging.getLogger(__name__)

# 保存时逐项覆盖的普通字段（密码单独处理）
PLAIN_FIELDS = ("host", "port", "tls", "username", "sender", "public_base_url")


@dataclass(frozen=True)
class MailChange:
    """只包含客户端明确传了的字段；None 表示不修改。password 为空串表示清除。"""

    host: str | None = None
    port: int | None = None
    tls: str | None = None
    username: str | None = None
    password: str | None = None
    sender: str | None = None
    public_base_url: str | None = None


def load_row(control: Session) -> MailSettings:
    """取设置行；不存在时按默认值创建。"""
    row = control.get(MailSettings, MAIL_SETTINGS_ROW_ID)
    if row is None:
        row = MailSettings(id=MAIL_SETTINGS_ROW_ID)
        control.add(row)
        control.flush()
    return row


def _encrypted_password(settings: Settings, password: str) -> str:
    if not password:
        return ""
    try:
        return encrypt_secret(settings, password)
    except SecretUnavailableError as error:
        raise AppError(str(error), status_code=400) from error


def update_mail_settings(
    control: Session, settings: Settings, change: MailChange, operator_id: int | None
) -> MailSettings:
    row = load_row(control)
    if change.password is not None:
        row.password_encrypted = _encrypted_password(settings, change.password)
    for name in PLAIN_FIELDS:
        value = getattr(change, name)
        if value is not None:
            setattr(row, name, value)
    row.updated_by = operator_id
    row.updated_at = now()
    control.flush()
    logger.info("邮件设置已由账号 #%s 修改（密码：%s）", operator_id, _password_action(change))
    return row


def _password_action(change: MailChange) -> str:
    if change.password is None:
        return "未改"
    return "已清除" if change.password == "" else "已更新"


def record_check(
    control: Session, kind: str, info: ErrorInfo, is_ok: bool, operator_id: int | None
) -> MailSettings:
    row = load_row(control)
    row.last_check_kind = kind
    row.last_check_ok = is_ok
    row.last_check_category = info.category
    row.last_check_message = info.message
    row.last_checked_by = operator_id
    row.last_checked_at = now()
    control.flush()
    logger.info("账号 #%s 执行了邮件%s测试：%s", operator_id, kind, info.category)
    return row
