"""服务器密文箱：加解密往返、密钥自动生成（0600）、环境变量密钥优先、密钥丢失友好报错。"""

import stat

import pytest
from cryptography.fernet import Fernet

from invoice_sorting.common.secret_box import (
    MSG_DECRYPT_FAILED,
    MSG_ENV_KEY_INVALID,
    MSG_KEY_MISSING,
    SecretUnavailableError,
    decrypt_secret,
    encrypt_secret,
    load_fernet,
)
from tests.conftest import make_settings

PLAINTEXT = "smtp-授权码-123"


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.delenv("INVOICE_SORTING_SECRET_KEY", raising=False)
    return make_settings(tmp_path)


def test_encrypt_then_decrypt_round_trips(settings):
    token = encrypt_secret(settings, PLAINTEXT)

    assert PLAINTEXT not in token
    assert decrypt_secret(settings, token) == PLAINTEXT


def test_key_file_generated_on_first_encrypt_with_0600(settings):
    assert not settings.secret_key_path.exists()

    encrypt_secret(settings, PLAINTEXT)

    mode = stat.S_IMODE(settings.secret_key_path.stat().st_mode)
    assert mode == 0o600
    Fernet(settings.secret_key_path.read_bytes())  # 合法的 Fernet 密钥


def test_existing_key_file_is_reused_not_overwritten(settings):
    token = encrypt_secret(settings, PLAINTEXT)
    original = settings.secret_key_path.read_bytes()

    encrypt_secret(settings, "another")

    assert settings.secret_key_path.read_bytes() == original
    assert decrypt_secret(settings, token) == PLAINTEXT


def test_env_key_takes_priority_and_no_file_is_written(tmp_path):
    key = Fernet.generate_key().decode()
    settings = make_settings(tmp_path, secret_key=key)

    token = encrypt_secret(settings, PLAINTEXT)

    assert not settings.secret_key_path.exists()
    assert Fernet(key.encode()).decrypt(token.encode()).decode() == PLAINTEXT


def test_env_key_read_from_environment(tmp_path, monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("INVOICE_SORTING_SECRET_KEY", key)
    settings = make_settings(tmp_path)

    token = encrypt_secret(settings, PLAINTEXT)

    assert Fernet(key.encode()).decrypt(token.encode()).decode() == PLAINTEXT
    assert key not in repr(settings)


def test_invalid_env_key_raises_friendly_error(tmp_path):
    settings = make_settings(tmp_path, secret_key="not-a-fernet-key")

    with pytest.raises(SecretUnavailableError) as caught:
        encrypt_secret(settings, PLAINTEXT)

    assert str(caught.value) == MSG_ENV_KEY_INVALID


def test_missing_key_file_raises_friendly_error_on_decrypt(settings):
    token = encrypt_secret(settings, PLAINTEXT)
    settings.secret_key_path.unlink()

    with pytest.raises(SecretUnavailableError) as caught:
        decrypt_secret(settings, token)

    assert str(caught.value) == MSG_KEY_MISSING
    assert not settings.secret_key_path.exists()  # 解密时不偷偷生成新密钥


def test_replaced_key_cannot_decrypt_old_token(settings):
    token = encrypt_secret(settings, PLAINTEXT)
    settings.secret_key_path.write_bytes(Fernet.generate_key())

    with pytest.raises(SecretUnavailableError) as caught:
        decrypt_secret(settings, token)

    assert str(caught.value) == MSG_DECRYPT_FAILED


def test_load_without_create_does_not_generate(settings):
    with pytest.raises(SecretUnavailableError):
        load_fernet(settings)

    assert not settings.secret_key_path.exists()
