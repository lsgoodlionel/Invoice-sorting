"""邮件设置的字段校验：主机名、端口、发件人与站点地址；全部拒绝换行等控制字符（防头注入）。"""

import ipaddress
import re
from collections.abc import Callable
from email.utils import parseaddr
from urllib.parse import urlsplit

from pydantic_core import PydanticCustomError

from invoice_sorting.mail_settings.constants import (
    MSG_BASE_URL_FORMAT,
    MSG_HOST_FORMAT,
    MSG_NO_CONTROL_CHARS,
    MSG_NOTIFY_EMAIL_FORMAT,
    MSG_NOTIFY_TOO_MANY,
    MSG_SENDER_FORMAT,
    MSG_TOO_LONG,
    PORT_MAX,
    PORT_MIN,
)
from invoice_sorting.mailer.recipients import (
    NOTIFY_EMAILS_MAX,
    join_notify_emails,
    split_notify_emails,
)
from invoice_sorting.signup.codes import is_valid_email

HOST_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
HOST_PATTERN = re.compile(rf"{HOST_LABEL}(?:\.{HOST_LABEL})*")
CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
HTTP_SCHEMES = ("http", "https")
MSG_PORT_RANGE = f"端口需为 {PORT_MIN}–{PORT_MAX} 之间的整数"


def _fail(kind: str, message: str) -> PydanticCustomError:
    return PydanticCustomError(kind, message)


def text_field(label: str, limit: int) -> Callable[[str], str]:
    """去首尾空白；限制长度并拒绝控制字符。空串合法（表示清空该项）。"""

    def check(value: str) -> str:
        text = value.strip()
        if len(text) > limit:
            raise _fail("text_length", MSG_TOO_LONG.format(label=label, limit=limit))
        if CONTROL_CHARS.search(text):
            raise _fail("control_chars", MSG_NO_CONTROL_CHARS.format(label=label))
        return text

    return check


def is_valid_host(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return bool(HOST_PATTERN.fullmatch(host))


def check_host(value: str) -> str:
    if value and not is_valid_host(value):
        raise _fail("host_format", MSG_HOST_FORMAT)
    return value.lower()


def check_port(value: int) -> int:
    if not PORT_MIN <= value <= PORT_MAX:
        raise _fail("port_range", MSG_PORT_RANGE)
    return value


def check_sender(value: str) -> str:
    """邮箱地址，或「名称 <邮箱地址>」。"""
    if not value:
        return value
    address = parseaddr(value)[1]
    if not address or not is_valid_email(address):
        raise _fail("sender_format", MSG_SENDER_FORMAT)
    return value


def check_base_url(value: str) -> str:
    if not value:
        return value
    parts = urlsplit(value)
    if parts.scheme.lower() not in HTTP_SCHEMES or not parts.hostname:
        raise _fail("base_url_format", MSG_BASE_URL_FORMAT)
    if parts.query or parts.fragment or parts.username or parts.password:
        raise _fail("base_url_format", MSG_BASE_URL_FORMAT)
    return value.rstrip("/")


def check_notify_emails(value: str) -> str:
    """英文逗号分隔的多个邮箱：逐个校验格式并限制数量；存成去空白后的规范串。"""
    emails = split_notify_emails(value)
    if len(emails) > NOTIFY_EMAILS_MAX:
        raise _fail("notify_too_many", MSG_NOTIFY_TOO_MANY.format(limit=NOTIFY_EMAILS_MAX))
    for email in emails:
        if not is_valid_email(email):
            raise _fail("notify_format", MSG_NOTIFY_EMAIL_FORMAT.format(email=email))
    return join_notify_emails(emails)
