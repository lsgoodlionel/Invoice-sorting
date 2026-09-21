"""隐私：否决满 180 天清除个人资料（保留计数）；SMTP 密码不进日志、错误信息与诊断包。"""

import logging
import smtplib
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from invoice_sorting.db.models import now
from invoice_sorting.diagnostics.collect import collect_package
from invoice_sorting.diagnostics.constants import ENV_SET, MEMBER_ENV, REASON_MANUAL
from invoice_sorting.diagnostics.logging_setup import log_startup_summary
from invoice_sorting.signup.purge import purge_rejected, run_purge
from tests.diagnostics_helpers import FIXED_TIME, package_members, stub_commands
from tests.platform_helpers import login_platform
from tests.signup_helpers import (
    PLATFORM_APPLICATIONS,
    SMTP_PASSWORD,
    FakeTransport,
    application_rows,
    approve,
    install_transport,
    relax_apply_limit,
    signup_app,
    submit_ok,
    update_application,
)


@pytest.fixture
def app(tmp_path):
    app = signup_app(tmp_path)
    relax_apply_limit(app)
    return app


@pytest.fixture
def platform(app):
    return login_platform(app)


def _rejected(app, platform, email: str, days_ago: int) -> int:
    application_id = submit_ok(TestClient(app), email)["id"]
    platform.post(f"{PLATFORM_APPLICATIONS}/{application_id}/reject", json={"reason": "不符合"})
    update_application(app, application_id, reviewed_at=now() - timedelta(days=days_ago))
    return application_id


def test_purge_clears_personal_data_after_180_days(app, platform):
    old = _rejected(app, platform, "old@example.org", 181)
    recent = _rejected(app, platform, "new@example.org", 179)

    count = run_purge(app.state.control_session_factory)

    assert count == 1
    rows = {row.id: row for row in application_rows(app)}
    purged = rows[old]
    assert purged.is_purged and purged.purged_at is not None
    fields = (purged.name, purged.email, purged.identity, purged.needs, purged.ip_hash)
    assert fields == ("", "", "", "", "")
    assert purged.reject_reason == "" and purged.status == "rejected"
    assert rows[recent].email == "new@example.org" and not rows[recent].is_purged
    counts = platform.get(PLATFORM_APPLICATIONS).json()["data"]["counts"]
    assert counts["rejected"] == 2  # 保留统计计数


def test_purge_is_idempotent_and_skips_other_statuses(app, platform):
    application_id = submit_ok(TestClient(app))["id"]
    approve(platform, application_id)
    update_application(app, application_id, reviewed_at=now() - timedelta(days=400))

    with app.state.control_session_factory() as control:
        assert purge_rejected(control) == 0
    assert run_purge(app.state.control_session_factory) == 0


def test_purged_application_cannot_be_resent(app, platform):
    application_id = _rejected(app, platform, "old@example.org", 200)
    run_purge(app.state.control_session_factory)

    response = platform.post(f"{PLATFORM_APPLICATIONS}/{application_id}/resend")

    assert response.status_code == 409


def test_smtp_password_never_logged_or_returned(app, platform, caplog):
    # Arrange：服务器回显里故意带上密码，验证不会原样透出
    echo = f"auth failed for {SMTP_PASSWORD}".encode()
    install_transport(app, FakeTransport([smtplib.SMTPAuthenticationError(535, echo)]))
    application_id = submit_ok(TestClient(app))["id"]

    # Act
    with caplog.at_level(logging.DEBUG):
        log_startup_summary(app.state.settings)
        response = platform.post(f"{PLATFORM_APPLICATIONS}/{application_id}/approve", json={})
        logging.getLogger("test").info("配置：%s", app.state.settings)

    # Assert
    assert response.status_code == 200
    assert SMTP_PASSWORD not in response.text
    assert SMTP_PASSWORD not in caplog.text
    assert all(SMTP_PASSWORD not in row.mail_error for row in application_rows(app))
    assert "通知邮件发送失败" in caplog.text


def test_diagnostics_env_lists_smtp_names_without_values(tmp_path, monkeypatch):
    stub_commands(monkeypatch)
    monkeypatch.setenv("INVOICE_SORTING_SMTP_PASSWORD", SMTP_PASSWORD)
    monkeypatch.setenv("INVOICE_SORTING_SMTP_HOST", "smtp.invalid")
    app = signup_app(tmp_path)
    settings = app.state.settings
    settings.logs_dir.mkdir(parents=True, exist_ok=True)

    result = collect_package(settings, REASON_MANUAL, FIXED_TIME)

    members = package_members(result.path)
    assert f"INVOICE_SORTING_SMTP_PASSWORD  {ENV_SET}" in members[MEMBER_ENV]
    assert "INVOICE_SORTING_PUBLIC_BASE_URL" in members[MEMBER_ENV]
    assert all(SMTP_PASSWORD not in content for content in members.values())
