"""实测发现的三处邮件问题：未登录时的提示、服务器不支持登录/STARTTLS 的分类、环境变量只配一半。"""

import smtplib

import pytest

from invoice_sorting.mailer.errors import (
    CATEGORY_AUTH,
    CATEGORY_TLS,
    AuthNotSupportedError,
    StartTLSNotSupportedError,
    classify_error,
)
from tests.conftest import make_settings


def test_auth_not_supported_is_classified_as_auth_not_tls():
    info = classify_error(AuthNotSupportedError())

    assert info.category == CATEGORY_AUTH
    assert "不支持登录" in info.message


def test_starttls_not_supported_has_specific_hint():
    info = classify_error(StartTLSNotSupportedError())

    assert info.category == CATEGORY_TLS
    assert "STARTTLS" in info.message


def test_plain_ssl_error_still_tls():
    import ssl

    assert classify_error(ssl.SSLError()).category == CATEGORY_TLS


def test_transport_maps_login_not_supported(monkeypatch):
    from invoice_sorting.mailer import transport as module

    class FakeClient:
        def login(self, *_):
            raise smtplib.SMTPNotSupportedError("AUTH not supported")

    instance = object.__new__(module.SmtplibTransport)
    instance._config = type("C", (), {"user": "ops", "password": "x"})()

    with pytest.raises(AuthNotSupportedError):
        instance._login(FakeClient())


@pytest.mark.parametrize(
    ("host", "sender", "expected"),
    [
        ("smtp.example.com", "", True),
        ("", "noreply@example.com", True),
        ("smtp.example.com", "noreply@example.com", False),
        ("", "", False),
    ],
)
def test_env_incomplete_detection(tmp_path, host, sender, expected):
    settings = make_settings(tmp_path, smtp_host=host, smtp_from=sender)

    assert settings.is_smtp_env_incomplete is expected
