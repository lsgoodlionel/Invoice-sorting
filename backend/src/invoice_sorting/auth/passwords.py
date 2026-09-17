"""密码哈希：标准库 scrypt，自描述格式 scrypt$n=..,r=..,p=..$<salt_b64>$<hash_b64>。"""

import base64
import binascii
import hashlib
import hmac
import secrets

ALGORITHM = "scrypt"
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
DKLEN = 64
SALT_BYTES = 16
MAXMEM = 64 * 1024 * 1024
# 校验时接受的参数范围，防止被篡改的哈希串造成资源耗尽
MIN_N, MAX_N = 2**14, 2**20
MAX_R, MAX_P = 32, 16
PARAM_KEYS = ("n", "r", "p")


def _b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _derive(password: str, salt: bytes, n: int, r: int, p: int, dklen: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=MAXMEM, dklen=dklen
    )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _derive(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P, DKLEN)
    params = f"n={SCRYPT_N},r={SCRYPT_R},p={SCRYPT_P}"
    return f"{ALGORITHM}${params}${_b64encode(salt)}${_b64encode(digest)}"


def _parse_params(text: str) -> tuple[int, int, int] | None:
    pairs = [item.split("=", 1) for item in text.split(",")]
    if any(len(pair) != 2 for pair in pairs):
        return None
    values = dict(pairs)
    if sorted(values) != sorted(PARAM_KEYS) or len(pairs) != len(PARAM_KEYS):
        return None
    if not all(values[key].isdigit() for key in PARAM_KEYS):
        return None
    n, r, p = (int(values[key]) for key in PARAM_KEYS)
    is_power_of_two = n & (n - 1) == 0
    if not (MIN_N <= n <= MAX_N and is_power_of_two and 1 <= r <= MAX_R and 1 <= p <= MAX_P):
        return None
    return n, r, p


def _parse(encoded: str) -> tuple[tuple[int, int, int], bytes, bytes] | None:
    parts = encoded.split("$")
    if len(parts) != 4 or parts[0] != ALGORITHM:
        return None
    params = _parse_params(parts[1])
    try:
        salt = base64.b64decode(parts[2], validate=True)
        digest = base64.b64decode(parts[3], validate=True)
    except (binascii.Error, ValueError):
        return None
    if params is None or not salt or not digest:
        return None
    return params, salt, digest


def verify_password(password: str, encoded: str | None) -> bool:
    """校验密码；哈希串缺失或格式异常时安全返回 False。"""
    parsed = _parse(encoded) if encoded else None
    if parsed is None:
        return False
    (n, r, p), salt, expected = parsed
    try:
        actual = _derive(password, salt, n, r, p, len(expected))
    except (ValueError, MemoryError):
        return False
    return hmac.compare_digest(actual, expected)
