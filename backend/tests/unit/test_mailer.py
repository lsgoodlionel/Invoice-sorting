"""发信服务：未配置不发、重试上限、错误说明不带原文、传输层不在测试中联网。"""

import smtplib

import pytest

from invoice_sorting.mailer.resolve import env_config
from invoice_sorting.mailer.service import (
    MAX_ATTEMPTS,
    MSG_SERVER_REFUSED,
    MSG_TIMEOUT,
    Mailer,
    describe_error,
)
from invoice_sorting.mailer.transport import SmtpConfig, SmtplibTransport
from tests.conftest import make_settings
from tests.signup_helpers import SMTP_PASSWORD, SMTP_SETTINGS, FakeTransport


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path, **SMTP_SETTINGS)


def _mailer(settings, transport: FakeTransport, sleeps: list[float] | None = None) -> Mailer:
    record = sleeps if sleeps is not None else []
    return Mailer(env_config(settings), transport=transport, sleep=record.append)


def test_unconfigured_mailer_skips_without_touching_transport(tmp_path):
    transport = FakeTransport([AssertionError("不应被调用")])
    mailer = Mailer(env_config(make_settings(tmp_path)), transport=transport)

    result = mailer.send("a@example.org", "主题", "正文")

    assert result.status == "skipped" and not mailer.is_configured
    assert len(transport.errors) == 1


def test_sent_message_has_headers_and_body(settings):
    transport = FakeTransport()

    result = _mailer(settings, transport).send("a@example.org", "申请已通过", "链接")

    assert result.is_sent
    message = transport.messages[0]
    assert message["To"] == "a@example.org" and message["Subject"] == "申请已通过"
    assert "noreply@fp.example.com" in message["From"]
    assert message["Message-ID"].endswith("@fp.example.com>")
    assert message.get_content().strip() == "链接"


def test_transient_error_retries_once_then_succeeds(settings):
    sleeps: list[float] = []
    transport = FakeTransport([TimeoutError()])

    result = _mailer(settings, transport, sleeps).send("a@example.org", "s", "b")

    assert result.is_sent and len(sleeps) == 1


def test_gives_up_after_max_attempts(settings):
    transport = FakeTransport([TimeoutError()] * (MAX_ATTEMPTS + 1))

    result = _mailer(settings, transport).send("a@example.org", "s", "b")

    assert result.status == "failed" and result.error == MSG_TIMEOUT
    assert len(transport.errors) == 1


def test_describe_error_never_echoes_server_text():
    error = smtplib.SMTPDataError(554, f"rejected {SMTP_PASSWORD}".encode())

    text = describe_error(error)

    assert text == MSG_SERVER_REFUSED.format(code=554)
    assert SMTP_PASSWORD not in text


def test_smtp_config_repr_hides_password(settings):
    config = SmtpConfig.from_settings(settings)

    assert config.password == SMTP_PASSWORD
    assert SMTP_PASSWORD not in repr(config)
    assert SMTP_PASSWORD not in repr(settings)


def test_starttls_transport_logs_in_and_sends(monkeypatch, settings):
    calls: list[str] = []

    class FakeSmtp:
        def __init__(self, host, port, timeout):  # noqa: ANN001
            calls.append(f"connect {host}:{port} {timeout}")

        def ehlo(self):
            calls.append("ehlo")

        def starttls(self, context):  # noqa: ANN001
            calls.append("starttls")

        def login(self, user, password):  # noqa: ANN001
            calls.append(f"login {user}")

        def send_message(self, message):  # noqa: ANN001
            calls.append("send")

        def close(self):
            calls.append("close")

        def __enter__(self):
            return self

        def __exit__(self, *args):  # noqa: ANN002
            calls.append("quit")

    monkeypatch.setattr(smtplib, "SMTP", FakeSmtp)
    config = SmtpConfig("smtp.invalid", 587, "mailer", SMTP_PASSWORD, "starttls")

    SmtplibTransport(config).send(object())  # type: ignore[arg-type]

    assert calls == [
        "connect smtp.invalid:587 10.0",
        "ehlo",
        "starttls",
        "ehlo",
        "login mailer",
        "send",
        "quit",
    ]
