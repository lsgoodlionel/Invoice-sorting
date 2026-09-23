"""新申请待审批提醒：发给平台通知邮箱；不阻塞提交、失败只留痕、有每小时上限。"""

import logging

import pytest
from fastapi.testclient import TestClient

from invoice_sorting.auth.ratelimit import LoginRateLimiter
from invoice_sorting.control.signup_models import (
    NOTIFY_FAILED,
    NOTIFY_NONE,
    NOTIFY_SENT,
    NOTIFY_SKIPPED,
    NOTIFY_THROTTLED,
)
from invoice_sorting.signup.notify import (
    NOTIFY_MAX_PER_WINDOW,
    STATE_NOTIFY_LIMITER,
)
from tests.mail_helpers import MAIL_PATH, fresh_transport, platform_client, save, web_app
from tests.platform_helpers import login_platform
from tests.signup_helpers import (
    BASE_URL,
    SETTINGS_PATH,
    SMTP_PASSWORD,
    application_rows,
    relax_apply_limit,
    signup_app,
    submit_ok,
    transport_of,
)
from tests.tenancy_helpers import login_at

OPS_EMAIL = "ops@example.com"
PLATFORM_LINK = f"{BASE_URL}/platform?tab=applications"
ME = "/api/referrals/me"


@pytest.fixture
def app(tmp_path):
    """环境变量配置 SMTP 与通知邮箱（source=env）。"""
    app = signup_app(tmp_path, signup_notify_emails=OPS_EMAIL)
    relax_apply_limit(app)
    return app


@pytest.fixture
def visitor(app):
    return TestClient(app)


def last_alert(app):
    return transport_of(app).messages[-1]


def test_pending_application_alerts_notify_emails(app, visitor):
    data = submit_ok(visitor)

    message = last_alert(app)
    body = message.get_content()
    assert message["To"] == OPS_EMAIL
    assert data["number"] in message["Subject"]
    for text in (
        data["number"],
        "张三",
        "zhang@example.org",
        "某某大学 财务处",
        "课题组报销票据整理",
    ):
        assert text in body
    assert PLATFORM_LINK in body
    assert application_rows(app)[0].notify_status == NOTIFY_SENT


def test_alert_carries_no_credentials_or_register_link(app, visitor):
    submit_ok(visitor)

    body = last_alert(app).get_content()
    assert SMTP_PASSWORD not in body
    assert "/register?code=" not in body and "密码" not in body


def test_alert_names_the_referrer(app, visitor):
    referrer = TestClient(app)
    assert login_at(referrer, "alpha-admin", slug="alpha").status_code == 200
    code = referrer.get(ME).json()["data"]["code"]

    submit_ok(visitor, ref=code)

    body = last_alert(app).get_content()
    assert "alpha-admin" in body and "推荐人" in body


def test_auto_approved_direct_registration_sends_no_alert(app, visitor):
    platform = login_platform(app)
    referrer = TestClient(app)
    assert login_at(referrer, "alpha-admin", slug="alpha").status_code == 200
    code = referrer.get(ME).json()["data"]["code"]
    assert platform.patch(SETTINGS_PATH, json={"require_approval": False}).status_code == 200

    data = submit_ok(visitor, ref=code)

    assert data["status"] == "approved"
    messages = transport_of(app).messages
    assert len(messages) == 1 and messages[0]["To"] == "zhang@example.org"
    assert application_rows(app)[0].notify_status == NOTIFY_NONE


def test_no_alert_when_notify_emails_not_set(tmp_path):
    app = signup_app(tmp_path)  # 有 SMTP，没有通知邮箱
    visitor = TestClient(app)

    submit_ok(visitor)

    assert transport_of(app).messages == []
    assert application_rows(app)[0].notify_status == NOTIFY_SKIPPED


def test_no_alert_when_smtp_not_configured(tmp_path):
    app = web_app(tmp_path)
    platform = platform_client(app)
    assert platform.patch(MAIL_PATH, json={"notify_emails": OPS_EMAIL}).status_code == 200

    submit_ok(TestClient(app))

    assert transport_of(app).messages == []
    assert application_rows(app)[0].notify_status == NOTIFY_SKIPPED


def test_web_configured_notify_emails_receive_alert(tmp_path):
    app = web_app(tmp_path)
    save(platform_client(app), notify_emails=f" {OPS_EMAIL} , boss@example.com ")

    submit_ok(TestClient(app))

    message = transport_of(app).messages[-1]
    assert message["To"] == f"{OPS_EMAIL}, boss@example.com"
    assert "https://web.example.com/platform?tab=applications" in message.get_content()


def test_multiple_env_notify_emails_all_receive(tmp_path):
    app = signup_app(tmp_path, signup_notify_emails=f"{OPS_EMAIL}, boss@example.com")

    submit_ok(TestClient(app))

    assert transport_of(app).messages[-1]["To"] == f"{OPS_EMAIL}, boss@example.com"


def test_send_failure_keeps_submit_ok_and_records_status(app, visitor, caplog):
    fresh_transport(app, [TimeoutError(), TimeoutError()])

    with caplog.at_level(logging.WARNING):
        data = submit_ok(visitor)

    assert data["status"] == "pending"
    row = application_rows(app)[0]
    assert row.notify_status == NOTIFY_FAILED and "超时" in row.notify_error
    assert "提醒" in caplog.text


def test_rate_limit_skips_alerts_beyond_the_hourly_cap(app, visitor):
    assert NOTIFY_MAX_PER_WINDOW == 20
    limiter = LoginRateLimiter(max_failures=2, window_seconds=3600, lock_seconds=3600)
    setattr(app.state, STATE_NOTIFY_LIMITER, limiter)

    for index in range(3):
        submit_ok(visitor, email=f"visitor{index}@example.org")

    statuses = [row.notify_status for row in application_rows(app)]
    assert statuses == [NOTIFY_SENT, NOTIFY_SENT, NOTIFY_THROTTLED]
    assert len(transport_of(app).messages) == 2
