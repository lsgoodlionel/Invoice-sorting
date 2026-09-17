"""密码哈希：scrypt + 随机盐，自描述格式，校验异常安全。"""

import pytest

from invoice_sorting.auth.passwords import hash_password, verify_password


def test_hash_has_self_describing_format():
    encoded = hash_password("correct horse")
    algorithm, params, salt, digest = encoded.split("$")
    assert algorithm == "scrypt"
    assert params == "n=16384,r=8,p=1"
    assert salt and digest
    assert "correct horse" not in encoded


def test_same_password_gets_different_salt():
    assert hash_password("same-password") != hash_password("same-password")


def test_verify_accepts_correct_and_rejects_wrong():
    encoded = hash_password("s3cret-pass")
    assert verify_password("s3cret-pass", encoded) is True
    assert verify_password("s3cret-pasS", encoded) is False
    assert verify_password("", encoded) is False


@pytest.mark.parametrize(
    "encoded",
    [
        "",
        "garbage",
        "bcrypt$n=16384,r=8,p=1$AAAA$AAAA",
        "scrypt$n=16384,r=8$AAAA$AAAA",
        "scrypt$n=abc,r=8,p=1$AAAA$AAAA",
        "scrypt$n=16384,r=8,p=1$!!!$AAAA",
        "scrypt$n=16384,r=8,p=1$AAAA$",
        "scrypt$n=1048576000,r=8,p=1$AAAA$AAAA",
        "scrypt$n=1000,r=8,p=1$AAAA$AAAA",
        "scrypt$n=16384,r=8,p=1,x=2$AAAA$AAAA",
        "scrypt$n=16384,n=16384,r=8,p=1$AAAA$AAAA",
        "scrypt$n=16384,r8,p=1$AAAA$AAAA",
        "scrypt$n=16384,r=8,p=1$AAAA$AAAA$AAAA",
    ],
)
def test_verify_returns_false_for_malformed_hash(encoded):
    assert verify_password("whatever-pass", encoded) is False


def test_verify_returns_false_for_none():
    assert verify_password("whatever-pass", None) is False
