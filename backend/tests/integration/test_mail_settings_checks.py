"""测试连接与测试邮件：用当前生效配置、失败分类不回显原文、记录最近验证、测试邮件限流。"""

import smtplib
import ssl

import pytest

from invoice_sorting.config import SECRET_KEY_FILENAME
from tests.mail_helpers import (
    MAIL_PATH,
    TEST_CONNECTION,
    TEST_EMAIL,
    WEB_PASSWORD,
    fresh_transport,
    mail_row,
    platform_client,
    save,
    web_app,
)
from tests.platform_helpers import PLATFORM_ADMIN
from tests.signup_helpers import signup_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.delenv("INVOICE_SORTING_SECRET_KEY", raising=False)
    return web_app(tmp_path)


@pytest.fixture
def platform(app):
    client = platform_client(app)
    save(client)
    return client


def test_connection_ok_uses_saved_config_and_records_result(app, platform):
    transport = fresh_transport(app)

    response = platform.post(TEST_CONNECTION)

    data = response.json()["data"]
    assert response.status_code == 200 and data["ok"] and data["category"] == "ok"
    config = transport.configs[0]
    assert (config.host, config.port, config.user) == ("smtp.invalid", 465, "robot@fp.example.com")
    assert config.password == WEB_PASSWORD and transport.messages == []
    last = platform.get(MAIL_PATH).json()["data"]["last_check"]
    assert last["kind"] == "connection" and last["ok"] and last["checked_by"] == PLATFORM_ADMIN


@pytest.mark.parametrize(
    "error,category",
    [
        (TimeoutError(), "timeout"),
        (ConnectionRefusedError(61, "refused"), "connect"),
        (ssl.SSLError(1, "wrong version number"), "tls"),
        (smtplib.SMTPAuthenticationError(535, f"bad {WEB_PASSWORD}".encode()), "auth"),
        (RuntimeError(WEB_PASSWORD), "other"),
    ],
)
def test_connection_failures_are_classified_without_echo(app, platform, error, category):
    fresh_transport(app, [error])

    response = platform.post(TEST_CONNECTION)

    data = response.json()["data"]
    assert response.status_code == 200 and not data["ok"] and data["category"] == category
    assert WEB_PASSWORD not in response.text
    row = mail_row(app)
    assert row.last_check_category == category and not row.last_check_ok


def test_test_email_sends_to_given_address(app, platform):
    transport = fresh_transport(app)

    response = platform.post(TEST_EMAIL, json={"to": "Check@Example.org"})

    assert response.json()["data"]["ok"]
    message = transport.messages[0]
    assert message["To"] == "check@example.org"
    assert "robot@fp.example.com" in message["From"]
    assert mail_row(app).last_check_kind == "email"


def test_test_email_rejects_bad_address(platform):
    assert platform.post(TEST_EMAIL, json={"to": "not-mail"}).status_code == 422


def test_test_email_rate_limited_to_three_per_minute(app, platform):
    transport = fresh_transport(app)

    statuses = [
        platform.post(TEST_EMAIL, json={"to": "a@example.org"}).status_code for _ in range(4)
    ]

    assert statuses == [200, 200, 200, 429]
    assert len(transport.messages) == 3


def test_checks_without_configuration_are_409(tmp_path):
    app = web_app(tmp_path)
    client = platform_client(app)

    connection = client.post(TEST_CONNECTION)
    email = client.post(TEST_EMAIL, json={"to": "a@example.org"})

    assert (connection.status_code, email.status_code) == (409, 409)


def test_lost_key_reports_refill_password_instead_of_500(app, platform):
    transport = fresh_transport(app)
    (app.state.settings.data_dir / SECRET_KEY_FILENAME).unlink()

    response = platform.post(TEST_CONNECTION)

    data = response.json()["data"]
    assert response.status_code == 200 and data["category"] == "password"
    assert "请重新填写 SMTP 密码" in data["message"]
    assert transport.checks == 0


def test_checks_use_env_config_when_env_wins(tmp_path):
    app = signup_app(tmp_path)
    transport = fresh_transport(app)
    client = platform_client(app)

    response = client.post(TEST_CONNECTION)

    assert response.json()["data"]["ok"]
    assert transport.configs[0].user == "mailer"  # 环境变量里的账号
