"""防滥用：重复申请、诱饵字段、限流、注册码过期/重复使用/邮箱不符、重新发送换码。"""

import smtplib
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from invoice_sorting.control.repository import find_account
from invoice_sorting.db.models import now
from tests.platform_helpers import login_platform
from tests.signup_helpers import (
    APPLICATIONS,
    PLATFORM_APPLICATIONS,
    REGISTER,
    FakeTransport,
    application_rows,
    apply,
    apply_body,
    approve,
    code_from,
    install_transport,
    register_body,
    signup_app,
    submit_ok,
    transport_of,
    update_application,
)


@pytest.fixture
def app(tmp_path):
    return signup_app(tmp_path)


@pytest.fixture
def platform(app):
    return login_platform(app)


@pytest.fixture
def visitor(app):
    return TestClient(app)


def _approved_code(app, platform, visitor, email: str = "zhang@example.org") -> tuple[int, str]:
    application_id = submit_ok(visitor, email)["id"]
    approve(platform, application_id)
    return application_id, code_from(transport_of(app).last_body())


def test_same_email_cannot_apply_twice_while_pending(visitor):
    submit_ok(visitor)

    response = apply(visitor, "ZHANG@example.org ")

    assert response.status_code == 409
    assert response.json()["error"] == "该邮箱已有待审批的申请，请耐心等待审批结果"


def test_can_apply_again_after_rejection(platform, visitor):
    application_id = submit_ok(visitor)["id"]
    platform.post(f"{PLATFORM_APPLICATIONS}/{application_id}/reject", json={})

    assert apply(visitor).status_code == 200


def test_honeypot_is_silently_dropped(app, visitor):
    response = visitor.post(APPLICATIONS, json=apply_body(website="http://spam.example"))

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "pending"
    assert application_rows(app) == []


@pytest.mark.parametrize(
    "field,value",
    [("email", "not-an-email"), ("name", "   "), ("needs", ""), ("identity", "x" * 101)],
)
def test_invalid_fields_are_422(visitor, field, value):
    response = visitor.post(APPLICATIONS, json=apply_body(**{field: value}))

    assert response.status_code == 422


def test_apply_is_rate_limited_per_ip(visitor):
    statuses = [apply(visitor, f"u{i}@example.org").status_code for i in range(6)]

    assert statuses[:5] == [200] * 5
    assert statuses[5] == 429
    assert "提交过于频繁" in apply(visitor, "late@example.org").json()["error"]


def test_code_is_single_use(app, platform, visitor):
    _, code = _approved_code(app, platform, visitor)
    assert visitor.post(REGISTER, json=register_body(code)).status_code == 200

    again = TestClient(app).post(REGISTER, json=register_body(code, username="another"))
    peek = TestClient(app).get(REGISTER, params={"code": code})

    assert again.status_code == 409 and again.json()["error"] == "该注册链接已使用过，请直接登录"
    assert peek.status_code == 409


def test_expired_code_is_410(app, platform, visitor):
    application_id, code = _approved_code(app, platform, visitor)
    update_application(app, application_id, code_expires_at=now() - timedelta(minutes=1))

    response = visitor.post(REGISTER, json=register_body(code))

    assert response.status_code == 410
    assert response.json()["error"] == "注册链接已过期，请联系平台重新发送"


def test_email_must_match_application(app, platform, visitor):
    _, code = _approved_code(app, platform, visitor)

    response = visitor.post(REGISTER, json=register_body(code, email="other@example.org"))

    assert response.status_code == 400
    assert response.json()["error"] == "邮箱与申请时填写的不一致"


def test_unknown_code_is_404(visitor):
    response = visitor.get(REGISTER, params={"code": "nope"})

    assert response.status_code == 404
    assert response.json()["error"] == "注册链接无效，请核对邮件中的链接"


def test_existing_username_is_rejected_and_code_stays_usable(app, platform, visitor):
    _, code = _approved_code(app, platform, visitor)

    taken = visitor.post(REGISTER, json=register_body(code, username="alpha-admin"))
    retry = visitor.post(REGISTER, json=register_body(code))

    assert taken.status_code == 409
    assert retry.status_code == 200
    with app.state.control_session_factory() as control:
        assert find_account(control, "alpha-admin").is_platform_admin is False


def test_code_guessing_is_rate_limited(visitor):
    statuses = [visitor.get(REGISTER, params={"code": f"x{i}"}).status_code for i in range(11)]

    assert statuses[:10] == [404] * 10
    assert statuses[10] == 429


def test_resend_reissues_code_and_old_link_dies(app, platform, visitor):
    application_id, old_code = _approved_code(app, platform, visitor)

    response = platform.post(f"{PLATFORM_APPLICATIONS}/{application_id}/resend")

    assert response.status_code == 200
    new_code = code_from(transport_of(app).last_body())
    assert new_code != old_code
    assert visitor.get(REGISTER, params={"code": old_code}).status_code == 404
    assert visitor.get(REGISTER, params={"code": new_code}).status_code == 200


def test_resend_pending_is_409(platform, visitor):
    application_id = submit_ok(visitor)["id"]

    response = platform.post(f"{PLATFORM_APPLICATIONS}/{application_id}/resend")

    assert response.status_code == 409


def test_resend_rejection_mail(app, platform, visitor):
    application_id = submit_ok(visitor)["id"]
    platform.post(f"{PLATFORM_APPLICATIONS}/{application_id}/reject", json={"reason": "重复"})

    response = platform.post(f"{PLATFORM_APPLICATIONS}/{application_id}/resend")

    assert response.status_code == 200
    assert len(transport_of(app).messages) == 2


def test_mail_failure_keeps_approval_and_can_be_resent(app, platform, visitor):
    # Arrange：连续两次连接失败（首次 + 重试）
    install_transport(app, FakeTransport([OSError("down"), OSError("down")]))
    application_id = submit_ok(visitor)["id"]

    # Act
    data = approve(platform, application_id)

    # Assert：审批照样生效，响应带链接供转告；重发成功后状态更新
    assert data["application"]["status"] == "approved"
    assert data["notice"]["mail_status"] == "failed"
    assert data["notice"]["mail_error"] == "无法连接邮件服务器"
    assert data["notice"]["link"] and data["application"]["mail_status"] == "failed"
    resent = platform.post(f"{PLATFORM_APPLICATIONS}/{application_id}/resend").json()["data"]
    assert resent["notice"]["mail_status"] == "sent"
    assert resent["application"]["mail_sent_at"]


def test_auth_failure_is_not_retried(app, platform, visitor):
    error = smtplib.SMTPAuthenticationError(535, b"bad credentials")
    transport = install_transport(app, FakeTransport([error, OSError("unused")]))
    application_id = submit_ok(visitor)["id"]

    data = approve(platform, application_id)

    assert data["notice"]["mail_error"] == "邮件服务器登录失败，请检查 SMTP 用户名与密码配置"
    assert len(transport.errors) == 1  # 第二个错误没被消耗：认证失败不重试
