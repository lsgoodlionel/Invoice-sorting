"""推荐：推荐链接、预填推荐人、需审批/直接注册两种模式、名额、重置与停用、实名记录。"""

import pytest
from fastapi.testclient import TestClient

from invoice_sorting.control.repository import find_account
from tests.platform_helpers import login_platform
from tests.signup_helpers import (
    BASE_URL,
    PLATFORM_APPLICATIONS,
    REGISTER,
    SETTINGS_PATH,
    code_from,
    register_body,
    relax_apply_limit,
    signup_app,
    submit_ok,
    transport_of,
)
from tests.tenancy_helpers import login_at

ME = "/api/referrals/me"
RESET = "/api/referrals/me/reset"
REFERRAL_RECORDS = "/api/platform/referrals"


@pytest.fixture
def app(tmp_path):
    app = signup_app(tmp_path)
    relax_apply_limit(app)
    return app


@pytest.fixture
def platform(app):
    return login_platform(app)


@pytest.fixture
def visitor(app):
    return TestClient(app)


@pytest.fixture
def referrer(app):
    client = TestClient(app)
    assert login_at(client, "alpha-admin", slug="alpha").status_code == 200
    return client


def _ref_code(referrer: TestClient) -> str:
    return referrer.get(ME).json()["data"]["code"]


def _direct_mode(platform: TestClient, quota: int = 5) -> None:
    body = {"require_approval": False, "monthly_referral_quota": quota}
    assert platform.patch(SETTINGS_PATH, json=body).status_code == 200


def test_me_creates_code_once_with_full_link(referrer):
    first = referrer.get(ME).json()["data"]
    second = referrer.get(ME).json()["data"]

    assert first["code"] == second["code"] and len(first["code"]) == 8
    assert first["link"] == f"{BASE_URL}/apply?ref={first['code']}"
    assert first["is_disabled"] is False and first["require_approval"] is True
    assert first["total"] == 0 and first["referrals"] == []


def test_referral_code_lookup_prefills_referrer(referrer, visitor):
    code = _ref_code(referrer)

    data = visitor.get(f"/api/signup/referral/{code.lower()}").json()["data"]

    assert data == {"code": code, "referrer_name": "alpha-admin", "require_approval": True}
    assert visitor.get("/api/signup/referral/ZZZZZZZZ").status_code == 404


def test_approval_mode_shows_referrer_in_platform(referrer, visitor, platform):
    code = _ref_code(referrer)

    submitted = submit_ok(visitor, ref=code)

    assert submitted["status"] == "pending" and submitted["referrer_name"] == "alpha-admin"
    detail = platform.get(f"{PLATFORM_APPLICATIONS}/{submitted['id']}").json()["data"]
    assert detail["referrer"]["username"] == "alpha-admin"
    assert detail["is_auto_approved"] is False


def test_referrer_sees_status_but_not_private_details(referrer, visitor, platform):
    submitted = submit_ok(visitor, ref=_ref_code(referrer))

    data = referrer.get(ME).json()["data"]

    assert data["total"] == 1
    item = data["referrals"][0]
    assert item == {
        "id": submitted["id"],
        "email_masked": "z***@example.org",
        "status": "pending",
        "created_at": item["created_at"],
        "registered_at": None,
    }
    text = str(data)
    assert "课题组报销票据整理" not in text and "张三" not in text


def test_direct_mode_issues_code_immediately_within_quota(app, referrer, visitor, platform):
    _direct_mode(platform, quota=1)
    code = _ref_code(referrer)

    first = submit_ok(visitor, "a@example.org", ref=code)
    second = submit_ok(visitor, "b@example.org", ref=code)

    assert first["status"] == "approved" and "注册链接已发送" in first["message"]
    assert second["status"] == "pending"  # 名额用尽，自动转审批
    register_code = code_from(transport_of(app).last_body())
    response = visitor.post(REGISTER, json=register_body(register_code, email="a@example.org"))
    assert response.status_code == 200
    me = referrer.get(ME).json()["data"]
    assert me["used_this_month"] == 1
    assert [item["status"] for item in me["referrals"]] == ["pending", "registered"]


def test_direct_mode_without_smtp_falls_back_to_approval(tmp_path):
    app = signup_app(tmp_path, with_smtp=False)
    platform = login_platform(app)
    _direct_mode(platform)
    referrer = TestClient(app)
    login_at(referrer, "alpha-admin", slug="alpha")

    submitted = submit_ok(TestClient(app), ref=_ref_code(referrer))

    assert submitted["status"] == "pending"


def test_direct_mode_without_referral_still_needs_approval(visitor, platform):
    _direct_mode(platform)

    assert submit_ok(visitor)["status"] == "pending"


def test_reset_invalidates_old_link(referrer, visitor):
    old = _ref_code(referrer)

    new = referrer.post(RESET).json()["data"]["code"]

    assert new != old
    assert visitor.get(f"/api/signup/referral/{old}").status_code == 404
    assert visitor.get(f"/api/signup/referral/{new}").status_code == 200
    assert visitor.post("/api/signup/applications", json={**_body(), "ref": old}).status_code == 404


def _body() -> dict:
    return {"name": "李四", "email": "li@example.org", "identity": "公司", "needs": "报销"}


def test_platform_can_disable_referrer(app, referrer, visitor, platform):
    code = _ref_code(referrer)
    with app.state.control_session_factory() as control:
        account_id = find_account(control, "alpha-admin").id

    response = platform.patch(f"/api/platform/referrers/{account_id}", json={"is_disabled": True})

    assert response.json()["data"] == {"account_id": account_id, "is_disabled": True}
    assert visitor.get(f"/api/signup/referral/{code}").status_code == 404
    me = referrer.get(ME).json()["data"]
    assert me["is_disabled"] is True and me["code"] is None and me["link"] is None
    assert referrer.post(RESET).status_code == 403
    platform.patch(f"/api/platform/referrers/{account_id}", json={"is_disabled": False})
    assert visitor.get(f"/api/signup/referral/{code}").status_code == 200


def test_disable_unknown_account_is_404(platform):
    response = platform.patch("/api/platform/referrers/9999", json={"is_disabled": True})

    assert response.status_code == 404


def test_platform_referral_records_are_real_name(app, referrer, visitor, platform):
    code = _ref_code(referrer)
    submit_ok(visitor, "a@example.org", ref=code)
    submit_ok(visitor, "plain@example.org")  # 无推荐人的申请不出现在推荐记录里

    data = platform.get(REFERRAL_RECORDS).json()["data"]
    searched = platform.get(REFERRAL_RECORDS, params={"q": "alpha-admin"}).json()["data"]

    assert data["total"] == 1
    record = data["items"][0]
    assert record["referrer"]["username"] == "alpha-admin"
    assert record["referee_email"] == "a@example.org"
    assert record["status"] == "pending" and record["tenant"] is None
    assert record["is_referrer_disabled"] is False
    assert searched["total"] == 1


def test_signup_settings_read_and_validate(platform):
    data = platform.get(SETTINGS_PATH).json()["data"]

    assert data["require_approval"] is True
    assert data["monthly_referral_quota"] == 5 and data["code_valid_days"] == 7
    assert data["is_mail_configured"] is True
    assert "ip_salt" not in data
    assert platform.patch(SETTINGS_PATH, json={"code_valid_days": 0}).status_code == 422
    changed = platform.patch(SETTINGS_PATH, json={"code_valid_days": 3}).json()["data"]
    assert changed["code_valid_days"] == 3 and changed["require_approval"] is True
