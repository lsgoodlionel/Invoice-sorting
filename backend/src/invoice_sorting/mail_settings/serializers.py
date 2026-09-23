"""邮件设置的响应：**永不包含密码或其密文**，只给 password_set 与无法解密时的提示。"""

from typing import Any

from sqlalchemy.orm import Session

from invoice_sorting.attachments.serializers import iso_datetime
from invoice_sorting.config import DEFAULT_SMTP_PORT, SMTP_TLS_SSL, Settings
from invoice_sorting.control.mail_models import MailSettings
from invoice_sorting.control.repository import get_account
from invoice_sorting.mail_settings.constants import MSG_ENV_INCOMPLETE
from invoice_sorting.mailer.resolve import SOURCE_ENV, ResolvedMail, read_password


def _account_name(control: Session, account_id: int | None) -> str:
    if account_id is None:
        return ""
    account = get_account(control, account_id)
    if account is None:
        return ""
    return account.display_name or account.username


def _env_fields(settings: Settings) -> dict[str, Any]:
    return {
        "host": settings.smtp_host.strip(),
        "port": settings.smtp_port,
        "tls": settings.smtp_tls,
        "username": settings.smtp_user.strip(),
        "sender": settings.smtp_from.strip(),
        "public_base_url": settings.public_base_url.strip(),
        "notify_emails": settings.signup_notify_emails.strip(),
        "password_set": bool(settings.smtp_password.get_secret_value()),
        "password_error": "",
        "updated_at": None,
        "updated_by": "",
    }


def _web_fields(control: Session, settings: Settings, row: MailSettings | None) -> dict[str, Any]:
    if row is None:
        return {
            "host": "",
            "port": DEFAULT_SMTP_PORT,
            "tls": SMTP_TLS_SSL,
            "username": "",
            "sender": "",
            "public_base_url": "",
            "notify_emails": "",
            "password_set": False,
            "password_error": "",
            "updated_at": None,
            "updated_by": "",
        }
    return {
        "host": row.host,
        "port": row.port,
        "tls": row.tls,
        "username": row.username,
        "sender": row.sender,
        "public_base_url": row.public_base_url,
        "notify_emails": row.notify_emails,
        "password_set": bool(row.password_encrypted),
        "password_error": read_password(settings, row).error,
        "updated_at": iso_datetime(row.updated_at),
        "updated_by": _account_name(control, row.updated_by),
    }


def _last_check(control: Session, row: MailSettings | None) -> dict[str, Any] | None:
    if row is None or row.last_checked_at is None:
        return None
    return {
        "kind": row.last_check_kind,
        "ok": row.last_check_ok,
        "category": row.last_check_category,
        "message": row.last_check_message,
        "checked_at": iso_datetime(row.last_checked_at),
        "checked_by": _account_name(control, row.last_checked_by),
    }


def serialize_mail_settings(
    control: Session, settings: Settings, row: MailSettings | None, resolved: ResolvedMail
) -> dict[str, Any]:
    is_env = resolved.source == SOURCE_ENV
    fields = _env_fields(settings) if is_env else _web_fields(control, settings, row)
    return {
        "source": resolved.source,
        "is_configured": resolved.is_configured,
        "warning": MSG_ENV_INCOMPLETE if settings.is_smtp_env_incomplete else "",
        **fields,
        "last_check": _last_check(control, row),
    }


def serialize_check(row: MailSettings, is_ok: bool) -> dict[str, Any]:
    return {
        "ok": is_ok,
        "category": row.last_check_category,
        "message": row.last_check_message,
        "checked_at": iso_datetime(row.last_checked_at),
    }
