"""授权令牌：Ed25519 签名的紧凑令牌 `base64url(载荷).base64url(签名)`。

载荷是排序后的紧凑 JSON，签名针对这份**原始字节**，验签时按同样字节比对，
因此中途任何改动都会导致验签失败。除验签外还要校验密钥与实例的绑定关系及签发时间
（防重放），三项全过才接受。
"""

import base64
import binascii
import json
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field, field_validator

from invoice_sorting.db.models import TZ
from invoice_sorting.licensing.keys import is_signature_valid, sign

# 令牌应当是刚刚签发的：过旧视为重放，过新视为时钟异常
MAX_ISSUED_AGE = timedelta(hours=1)
MAX_CLOCK_SKEW = timedelta(minutes=5)
TOKEN_PARTS = 2
MAX_TOKEN_LENGTH = 4096

MSG_MALFORMED = "令牌格式不正确"
MSG_BAD_SIGNATURE = "令牌签名校验失败"
MSG_KEY_MISMATCH = "令牌与本机授权密钥不一致"
MSG_INSTANCE_MISMATCH = "令牌与本机实例不一致"
MSG_TOO_OLD = "令牌签发时间过旧，已拒绝"
MSG_FROM_FUTURE = "令牌签发时间异常，已拒绝"
MSG_REPLAYED = "令牌早于已保存的授权，已拒绝"


class LicenseTokenError(Exception):
    """令牌不可信；message 面向运维日志，不直接回给终端用户。"""


class LicenseClaims(BaseModel):
    """令牌载荷。valid_until 为 None 表示永久授权。"""

    license_key: str = Field(min_length=1, max_length=128)
    instance_id: str = Field(min_length=1, max_length=64)
    valid_until: datetime | None = None
    max_users: int = Field(default=0, ge=0)
    features: dict[str, Any] = Field(default_factory=dict)
    issued_at: datetime

    @field_validator("valid_until", "issued_at")
    @classmethod
    def _as_aware(cls, value: datetime | None) -> datetime | None:
        """SQLite 与部分序列化会丢时区，统一按 Asia/Shanghai 补齐。"""
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=TZ)
        return value


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64decode(text: str) -> bytes:
    padded = text + "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(padded)


def canonical_payload(claims: LicenseClaims) -> bytes:
    """签名对象：键排序、无多余空白的紧凑 JSON。"""
    data = claims.model_dump(mode="json")
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def encode_token(claims: LicenseClaims, private_key: Any) -> str:
    payload = canonical_payload(claims)
    return f"{_b64encode(payload)}.{_b64encode(sign(private_key, payload))}"


def decode_token(raw: str, public_key: Any) -> LicenseClaims:
    """验签并解析令牌；任何异常都收敛为 LicenseTokenError。"""
    if not raw or len(raw) > MAX_TOKEN_LENGTH:
        raise LicenseTokenError(MSG_MALFORMED)
    parts = raw.split(".")
    if len(parts) != TOKEN_PARTS:
        raise LicenseTokenError(MSG_MALFORMED)
    try:
        payload = _b64decode(parts[0])
        signature = _b64decode(parts[1])
    except (binascii.Error, ValueError) as error:
        raise LicenseTokenError(MSG_MALFORMED) from error
    if not is_signature_valid(public_key, payload, signature):
        raise LicenseTokenError(MSG_BAD_SIGNATURE)
    return _parse_payload(payload)


def _parse_payload(payload: bytes) -> LicenseClaims:
    try:
        return LicenseClaims.model_validate(json.loads(payload))
    except (ValueError, UnicodeDecodeError) as error:
        raise LicenseTokenError(MSG_MALFORMED) from error


def verify_claims(
    claims: LicenseClaims,
    license_key: str,
    instance_id: str,
    moment: datetime,
    previous_issued_at: datetime | None,
) -> None:
    """校验令牌与本机的绑定关系与新鲜度；不通过即抛出。"""
    if claims.license_key != license_key:
        raise LicenseTokenError(MSG_KEY_MISMATCH)
    if claims.instance_id != instance_id:
        raise LicenseTokenError(MSG_INSTANCE_MISMATCH)
    if claims.issued_at < moment - MAX_ISSUED_AGE:
        raise LicenseTokenError(MSG_TOO_OLD)
    if claims.issued_at > moment + MAX_CLOCK_SKEW:
        raise LicenseTokenError(MSG_FROM_FUTURE)
    if previous_issued_at is not None and claims.issued_at < previous_issued_at:
        raise LicenseTokenError(MSG_REPLAYED)
