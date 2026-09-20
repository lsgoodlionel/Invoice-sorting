"""授权测试辅助：用测试私钥本地签发令牌、伪造授权服务器、关闭后台定时。

私钥仅用于测试，对应 licensing/keys.py 内置的测试公钥；正式部署必须替换这对密钥。
"""

import base64
from datetime import datetime, timedelta
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from invoice_sorting.db.models import now
from invoice_sorting.licensing import client as license_client
from invoice_sorting.licensing import scheduler as license_scheduler
from invoice_sorting.licensing.client import VerifyOutcome
from invoice_sorting.licensing.token import LicenseClaims, encode_token

TEST_PRIVATE_KEY_B64 = "4u6s9NuM/pfMYmS477BsVPOXw0GO9Z+Jd30MCE88yYs="
TEST_LICENSE_KEY = "TEST-LICENSE-0001"


def test_private_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(base64.b64decode(TEST_PRIVATE_KEY_B64))


def make_claims(
    license_key: str = TEST_LICENSE_KEY,
    instance_id: str = "instance-1",
    days_valid: int | None = 30,
    max_users: int = 5,
    features: dict[str, Any] | None = None,
    issued_at: datetime | None = None,
) -> LicenseClaims:
    """构造授权声明；days_valid 为 None 表示永久授权，负数表示已过期。"""
    moment = issued_at or now()
    return LicenseClaims(
        license_key=license_key,
        instance_id=instance_id,
        valid_until=None if days_valid is None else moment + timedelta(days=days_valid),
        max_users=max_users,
        features=features or {},
        issued_at=moment,
    )


def sign_claims(claims: LicenseClaims) -> str:
    return encode_token(claims, test_private_key())


def make_token(**kwargs: Any) -> str:
    return sign_claims(make_claims(**kwargs))


def token_outcome(**kwargs: Any) -> VerifyOutcome:
    return VerifyOutcome(token=make_token(**kwargs))


def install_verifier(monkeypatch, responder) -> list[Any]:
    """替换网络校验函数，记录每次请求；测试永远不会真实联网。"""
    calls: list[Any] = []

    def fake(server: str, request: Any) -> VerifyOutcome:
        calls.append((server, request))
        return responder(request) if callable(responder) else responder

    monkeypatch.setattr(license_client, "verify_with_server", fake)
    return calls


def disable_scheduler(monkeypatch) -> None:
    """关闭后台定时线程，避免测试期间出现不确定的并发写入。"""
    monkeypatch.setattr(license_scheduler.LicenseScheduler, "start", lambda self: None)
