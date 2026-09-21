"""注册码、推荐码、IP 哈希与邮箱脱敏等纯函数（无数据库依赖）。"""

import hashlib
import hmac
import re
import secrets
from datetime import datetime

from invoice_sorting.db.models import TZ

REGISTER_CODE_BYTES = 24
REFERRAL_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 去掉易混的 I/O/0/1
REFERRAL_LENGTH = 8
IP_SALT_BYTES = 16
APPLICATION_NUMBER_PREFIX = "SQ"
APPLICATION_NUMBER_WIDTH = 6
MASK = "***"
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+$")


def new_register_code() -> str:
    return secrets.token_urlsafe(REGISTER_CODE_BYTES)


def hash_code(code: str) -> str:
    return hashlib.sha256((code or "").strip().encode("utf-8")).hexdigest()


def new_referral_code() -> str:
    return "".join(secrets.choice(REFERRAL_ALPHABET) for _ in range(REFERRAL_LENGTH))


def normalize_referral_code(code: str) -> str:
    return (code or "").strip().upper()


def new_ip_salt() -> str:
    return secrets.token_hex(IP_SALT_BYTES)


def hash_ip(ip: str, salt: str) -> str:
    """带实例盐的 HMAC：同一 IP 可归并统计，但无法由哈希反推出地址。"""
    return hmac.new(salt.encode("utf-8"), (ip or "").encode("utf-8"), hashlib.sha256).hexdigest()


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_PATTERN.fullmatch(email or ""))


def mask_email(email: str) -> str:
    """推荐人看到的被推荐人邮箱：只留首字符与域名，例如 z***@example.com。"""
    local, _, domain = (email or "").partition("@")
    if not local or not domain:
        return MASK
    return f"{local[0]}{MASK}@{domain}"


def application_number(application_id: int) -> str:
    return f"{APPLICATION_NUMBER_PREFIX}{application_id:0{APPLICATION_NUMBER_WIDTH}d}"


def aware(value: datetime | None) -> datetime | None:
    """SQLite 读回的时间不带时区（写入时为 Asia/Shanghai 墙钟时间）。"""
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=TZ)
