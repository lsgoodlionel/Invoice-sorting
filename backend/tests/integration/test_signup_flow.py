"""注册申请主流程：申请 → 审批 → 通知（已配置/未配置 SMTP）→ 凭码注册并开通独立账套。"""

import pytest
from fastapi.testclient import TestClient

from invoice_sorting.control.members import find_member
from invoice_sorting.control.repository import find_account, find_tenant
from invoice_sorting.control.signup_models import SignupApplication
from tests.platform_helpers import login_platform
from tests.signup_helpers import (
    BASE_URL,
    PLATFORM_APPLICATIONS,
    REGISTER,
    application_rows,
    approve,
    code_from,
    register_body,
    signup_app,
    submit_ok,
    transport_of,
)
from tests.tenancy_helpers import login_at


@pytest.fixture
def app(tmp_path):
    return signup_app(tmp_path)


@pytest.fixture
def platform(app):
    return login_platform(app)


@pytest.fixture
def visitor(app):
    return TestClient(app)


def test_submit_returns_number_and_pending_status(visitor, app):
    data = submit_ok(visitor)

    assert data["status"] == "pending"
    assert data["number"] == f"SQ{data['id']:06d}"
    assert "邮箱" in data["message"]
    row = application_rows(app)[0]
    assert row.email == "zhang@example.org" and row.needs == "课题组报销票据整理"
    assert row.ip_hash and "testclient" not in row.ip_hash  # 只存哈希，不存明文 IP


def test_approve_sends_mail_then_register_opens_own_tenant(app, platform, visitor):
    # Arrange
    application_id = submit_ok(visitor)["id"]

    # Act：批准并发信
    data = approve(platform, application_id)

    # Assert：邮件含注册链接与有效期，响应不回显链接
    assert data["notice"] == {"mail_status": "sent", "mail_error": "", "link": None, "text": None}
    assert data["application"]["status"] == "approved"
    assert data["application"]["reviewer"]["username"] == "ops-admin"
    message = transport_of(app).messages[-1]
    assert message["To"] == "zhang@example.org"
    body = message.get_content()
    assert f"{BASE_URL}/register?code=" in body and "有效期至" in body
    assert "课题组报销票据整理" not in body  # 邮件不含申请资料

    # Act：凭码注册
    code = code_from(body)
    info = visitor.get(REGISTER, params={"code": code}).json()["data"]
    response = visitor.post(REGISTER, json=register_body(code))

    # Assert：直接登录进入新开通的独立账套，本人为管理员、默认免费套餐
    assert info["email"] == "zhang@example.org" and info["ledger_name"] == "张三课题组"
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["user"]["username"] == "zhangsan" and payload["user"]["role"] == "admin"
    slug = payload["tenant"]["slug"]
    assert payload["tenant"]["name"] == "张三课题组"
    with app.state.control_session_factory() as control:
        tenant = find_tenant(control, slug)
        account = find_account(control, "zhangsan")
        assert find_member(control, account.id, tenant.id).role == "admin"
        assert tenant.plan_id is not None
    me = visitor.get("/api/auth/status").json()["data"]
    assert me["authenticated"] is True and me["tenant"]["slug"] == slug
    assert login_at(TestClient(app), "zhangsan", "zhang-pass-123").status_code == 200


def test_register_marks_application_and_platform_sees_tenant(app, platform, visitor):
    application_id = submit_ok(visitor)["id"]
    approve(platform, application_id, slug="zhang-lab", name="张三实验室", expires_on="2027-12-31")
    code = code_from(transport_of(app).last_body())

    visitor.post(REGISTER, json=register_body(code))

    detail = platform.get(f"{PLATFORM_APPLICATIONS}/{application_id}").json()["data"]
    assert detail["status"] == "registered"
    assert detail["tenant"] == {"slug": "zhang-lab", "name": "张三实验室"}
    assert detail["approved"]["expires_on"] == "2027-12-31"
    tenant = platform.get("/api/platform/tenants/zhang-lab").json()["data"]
    assert tenant["expires_on"] == "2027-12-31" and tenant["plan"]["code"] == "free"


def test_approve_without_smtp_returns_link_and_copyable_text(tmp_path):
    app = signup_app(tmp_path, with_smtp=False)
    visitor, platform = TestClient(app), login_platform(app)
    application_id = submit_ok(visitor)["id"]

    data = approve(platform, application_id)

    notice = data["notice"]
    assert notice["mail_status"] == "skipped"
    assert notice["link"].startswith("/register?code=")
    assert notice["link"] in notice["text"] and "有效期至" in notice["text"]
    assert transport_of(app).messages == []
    code = code_from(notice["link"])
    assert visitor.post(REGISTER, json=register_body(code)).status_code == 200


def test_approve_with_taken_slug_is_rejected(platform, visitor):
    application_id = submit_ok(visitor)["id"]

    response = platform.post(
        f"{PLATFORM_APPLICATIONS}/{application_id}/approve", json={"slug": "alpha"}
    )

    assert response.status_code == 409
    assert response.json()["error"] == "账套标识已被占用"


def test_approve_with_unknown_plan_is_404(platform, visitor):
    application_id = submit_ok(visitor)["id"]

    response = platform.post(
        f"{PLATFORM_APPLICATIONS}/{application_id}/approve", json={"plan_code": "nope"}
    )

    assert response.status_code == 404


def test_approve_twice_conflicts(platform, visitor):
    application_id = submit_ok(visitor)["id"]
    approve(platform, application_id)

    response = platform.post(f"{PLATFORM_APPLICATIONS}/{application_id}/approve", json={})

    assert response.status_code == 409
    assert response.json()["error"] == "该申请已处理，不能重复审批"


def test_reject_with_reason_notifies_and_records_reviewer(app, platform, visitor):
    application_id = submit_ok(visitor)["id"]

    response = platform.post(
        f"{PLATFORM_APPLICATIONS}/{application_id}/reject", json={"reason": "资料不完整"}
    )

    data = response.json()["data"]
    assert data["application"]["status"] == "rejected"
    assert data["application"]["reject_reason"] == "资料不完整"
    assert data["application"]["reviewer"]["username"] == "ops-admin"
    assert data["application"]["reviewed_at"]
    assert data["notice"]["mail_status"] == "sent"
    body = transport_of(app).last_body()
    assert "未通过" in body and "资料不完整" in body and "/register" not in body


def test_reject_without_reason_is_allowed(app, platform, visitor):
    application_id = submit_ok(visitor)["id"]

    response = platform.post(f"{PLATFORM_APPLICATIONS}/{application_id}/reject", json={})

    assert response.status_code == 200
    assert "原因" not in transport_of(app).last_body()


def test_list_filters_status_searches_and_counts(platform, visitor, app):
    first = submit_ok(visitor, "a@example.org", name="甲")["id"]
    submit_ok(visitor, "b@example.org", name="乙")
    platform.post(f"{PLATFORM_APPLICATIONS}/{first}/reject", json={})

    pending = platform.get(PLATFORM_APPLICATIONS, params={"status": "pending"}).json()["data"]
    searched = platform.get(PLATFORM_APPLICATIONS, params={"q": "a@example"}).json()["data"]

    assert [item["name"] for item in pending["items"]] == ["乙"]
    assert pending["counts"] == {"pending": 1, "approved": 0, "rejected": 1, "registered": 0}
    assert [item["id"] for item in searched["items"]] == [first]
    bad = platform.get(PLATFORM_APPLICATIONS, params={"status": "weird"})
    assert bad.status_code == 422


def test_unknown_application_is_404(platform):
    assert platform.get(f"{PLATFORM_APPLICATIONS}/999").status_code == 404


def test_rows_keep_reviewer_and_time(app, platform, visitor):
    application_id = submit_ok(visitor)["id"]
    approve(platform, application_id)

    row: SignupApplication = application_rows(app)[0]
    assert row.reviewer_account_id is not None and row.reviewed_at is not None
    assert row.code_hash and len(row.code_hash) == 64  # 注册码只存 SHA-256
