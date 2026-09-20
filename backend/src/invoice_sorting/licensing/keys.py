"""Ed25519 密钥装载。

- **公钥**内置于代码（可用环境变量覆盖），私有化实例据此验签。
- **私钥**只在 SaaS 控制面，从环境变量 `INVOICE_SORTING_LICENSE_PRIVATE_KEY`（base64 原始 32 字节）
  读取，任何情况下都不落盘、不入库、不写日志。

内置的这对密钥是**测试密钥**（私钥见 tests/license_helpers.py）。正式发布前必须
重新生成一对，把新公钥写入 DEFAULT_PUBLIC_KEY_B64，私钥只配置在控制面环境变量里。
"""

import base64
import binascii
import logging
import os

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

logger = logging.getLogger(__name__)

ENV_PRIVATE_KEY = "INVOICE_SORTING_LICENSE_PRIVATE_KEY"
ENV_PUBLIC_KEY = "INVOICE_SORTING_LICENSE_PUBLIC_KEY"
DEFAULT_PUBLIC_KEY_B64 = "fE4il5b7JUPfxyo6rO3x7E9FlB6QL6WBi1R1AuhPSQA="

MSG_PUBLIC_KEY_INVALID = "内置授权公钥不可用"


def _decode(text: str) -> bytes:
    return base64.b64decode(text.strip(), validate=True)


def load_public_key() -> Ed25519PublicKey:
    """验签公钥；环境变量配置错误时回退到内置公钥，不让应用起不来。"""
    configured = os.environ.get(ENV_PUBLIC_KEY, "").strip()
    if configured:
        try:
            return Ed25519PublicKey.from_public_bytes(_decode(configured))
        except (ValueError, binascii.Error):
            logger.warning("环境变量中的授权公钥无法解析，已回退到内置公钥")
    try:
        return Ed25519PublicKey.from_public_bytes(_decode(DEFAULT_PUBLIC_KEY_B64))
    except (ValueError, binascii.Error) as error:  # pragma: no cover - 代码常量损坏才会发生
        raise RuntimeError(MSG_PUBLIC_KEY_INVALID) from error


def load_private_key() -> Ed25519PrivateKey | None:
    """签发私钥；未配置或格式错误时返回 None（调用方据此返回 503）。"""
    configured = os.environ.get(ENV_PRIVATE_KEY, "").strip()
    if not configured:
        return None
    try:
        return Ed25519PrivateKey.from_private_bytes(_decode(configured))
    except (ValueError, binascii.Error):
        logger.error("授权签发私钥格式不正确（应为 base64 编码的 32 字节原始密钥）")
        return None


def sign(private_key: Ed25519PrivateKey, payload: bytes) -> bytes:
    return private_key.sign(payload)


def is_signature_valid(public_key: Ed25519PublicKey, payload: bytes, signature: bytes) -> bool:
    try:
        public_key.verify(signature, payload)
    except InvalidSignature:
        return False
    return True
