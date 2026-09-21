"""邮件测试的失败分类、字段校验与传输层 check（假 smtplib，绝不联网）。"""

import smtplib
import socket
import ssl

import pytest
from pydantic import ValidationError

from invoice_sorting.mail_settings.checks import check_connection, send_test_email
from invoice_sorting.mail_settings.schemas import MailSettingsPatch
from invoice_sorting.mailer.errors import (
    CATEGORY_AUTH,
    CATEGORY_CONNECT,
    CATEGORY_OK,
    CATEGORY_OTHER,
    CATEGORY_PASSWORD,
    CATEGORY_RECIPIENT,
    CATEGORY_SENDER,
    CATEGORY_TIMEOUT,
    CATEGORY_TLS,
    classify_error,
)
from invoice_sorting.mailer.service import MailConfig, MailerFactory
from invoice_sorting.mailer.transport import SmtpConfig, SmtplibTransport
from tests.signup_helpers import FakeTransport

SECRET = "Pw-in-server-echo-42"
CONFIG = MailConfig(
    smtp=SmtpConfig("smtp.invalid", 465, "robot", SECRET, "ssl"), sender="robot@fp.example.com"
)

CASES = [
    (smtplib.SMTPAuthenticationError(535, SECRET.encode()), CATEGORY_AUTH),
    (ssl.SSLError(1, "wrong version number"), CATEGORY_TLS),
    (smtplib.SMTPNotSupportedError("STARTTLS extension not supported"), CATEGORY_TLS),
    (TimeoutError("timed out"), CATEGORY_TIMEOUT),
    (ConnectionRefusedError(61, "refused"), CATEGORY_CONNECT),
    (socket.gaierror(8, "nodename nor servname"), CATEGORY_CONNECT),
    (smtplib.SMTPServerDisconnected("closed"), CATEGORY_CONNECT),
    (smtplib.SMTPSenderRefused(553, SECRET.encode(), "robot"), CATEGORY_SENDER),
    (smtplib.SMTPRecipientsRefused({"a@b.cn": (550, b"no")}), CATEGORY_RECIPIENT),
    (smtplib.SMTPDataError(554, SECRET.encode()), CATEGORY_OTHER),
    (ValueError(SECRET), CATEGORY_OTHER),
]


@pytest.mark.parametrize("error,category", CASES)
def test_classify_error_by_type_without_echo(error, category):
    info = classify_error(error)

    assert info.category == category
    assert SECRET not in info.message and info.message


@pytest.mark.parametrize("error,category", CASES[:6])
def test_check_connection_reports_category(error, category):
    factory = MailerFactory(transport_factory=FakeTransport([error]))

    outcome = check_connection(factory, CONFIG)

    assert not outcome.is_ok and outcome.info.category == category


def test_check_connection_success_does_not_send():
    transport = FakeTransport()

    outcome = check_connection(MailerFactory(transport_factory=transport), CONFIG)

    assert outcome.is_ok and outcome.info.category == CATEGORY_OK
    assert transport.checks == 1 and transport.messages == []


def test_unreadable_password_short_circuits_without_connecting():
    transport = FakeTransport()
    config = MailConfig(smtp=CONFIG.smtp, sender=CONFIG.sender, password_error="请重新填写")

    connection = check_connection(MailerFactory(transport_factory=transport), config)
    email = send_test_email(MailerFactory(transport_factory=transport), config, "a@b.cn")

    assert connection.info.category == email.info.category == CATEGORY_PASSWORD
    assert transport.configs == [] and transport.checks == 0


def test_test_email_is_chinese_and_says_it_is_a_test():
    transport = FakeTransport()

    outcome = send_test_email(MailerFactory(transport_factory=transport), CONFIG, "to@b.cn")

    assert outcome.is_ok
    message = transport.messages[0]
    assert message["To"] == "to@b.cn" and "测试" in message["Subject"]
    assert "测试邮件" in message.get_content()


class _RecordingSmtp:
    calls: list[str] = []

    def __init__(self, host, port, timeout, **_kwargs):  # noqa: ANN001, ANN003
        self.calls.append(f"connect {host}:{port} {timeout}")

    def ehlo(self):
        self.calls.append("ehlo")

    def starttls(self, context):  # noqa: ANN001
        self.calls.append("starttls")

    def login(self, user, password):  # noqa: ANN001
        self.calls.append(f"login {user}")

    def noop(self):
        self.calls.append("noop")

    def close(self):
        self.calls.append("close")

    def __enter__(self):
        return self

    def __exit__(self, *args):  # noqa: ANN002
        self.calls.append("quit")


@pytest.fixture
def recording(monkeypatch):
    _RecordingSmtp.calls = []
    monkeypatch.setattr(smtplib, "SMTP", _RecordingSmtp)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _RecordingSmtp)
    return _RecordingSmtp.calls


def test_plain_transport_check_skips_starttls(recording):
    SmtplibTransport(SmtpConfig("relay.invalid", 25, "u", SECRET, "none")).check()

    assert recording == ["connect relay.invalid:25 10.0", "ehlo", "login u", "noop", "quit"]


def test_ssl_transport_check_logs_in_without_sending(recording):
    SmtplibTransport(SmtpConfig("smtp.invalid", 465, "u", SECRET, "ssl")).check()

    assert recording == ["connect smtp.invalid:465 10.0", "login u", "noop", "quit"]


VALID = {"host": "smtp.qq.com", "port": 465, "sender": "机器人 <a@b.cn>"}


@pytest.mark.parametrize(
    "field,value",
    [
        ("host", "smtp..qq.com"),
        ("host", "smtp.qq.com\r\nRCPT"),
        ("host", "-bad.example.com"),
        ("port", 0),
        ("port", 65536),
        ("port", "465"),
        ("sender", "not-an-email"),
        ("sender", "a@b.cn\nBcc: x@y.cn"),
        ("public_base_url", "ftp://fp.example.com"),
        ("public_base_url", "fp.example.com"),
        ("public_base_url", "https://u:p@fp.example.com"),
        ("tls", "tls"),
    ],
)
def test_patch_rejects_invalid_values(field, value):
    with pytest.raises(ValidationError):
        MailSettingsPatch(**{**VALID, field: value})


def test_patch_accepts_ip_host_and_normalizes():
    body = MailSettingsPatch(
        host=" 10.0.0.5 ", public_base_url="https://fp.example.com/", sender="a@b.cn"
    )

    assert body.host == "10.0.0.5"
    assert body.public_base_url == "https://fp.example.com"


def test_patch_allows_empty_strings_to_clear():
    body = MailSettingsPatch(host="", sender="", public_base_url="", password="")

    assert (body.host, body.sender, body.public_base_url, body.password) == ("", "", "", "")
