"""权限边界：非平台管理员 403、未登录 401、单账套部署所有入口 404。"""

import pytest
from fastapi.testclient import TestClient

from tests.auth_helpers import setup_password
from tests.signup_helpers import (
    APPLICATIONS,
    PLATFORM_APPLICATIONS,
    REGISTER,
    SETTINGS_PATH,
    apply_body,
    signup_app,
    submit_ok,
)
from tests.tenancy_helpers import login_at

PLATFORM_READS = (PLATFORM_APPLICATIONS, "/api/platform/referrals", SETTINGS_PATH)


@pytest.fixture
def app(tmp_path):
    return signup_app(tmp_path)


@pytest.fixture
def tenant_admin(app):
    client = TestClient(app)
    assert login_at(client, "alpha-admin", slug="alpha").status_code == 200
    return client


@pytest.mark.parametrize("path", PLATFORM_READS)
def test_tenant_admin_cannot_read_platform_signup(tenant_admin, path):
    response = tenant_admin.get(path)

    assert response.status_code == 403
    assert response.json()["error"] == "需要平台管理员权限"


def test_tenant_admin_cannot_review_or_see_details(app, tenant_admin):
    application_id = submit_ok(TestClient(app))["id"]

    detail = tenant_admin.get(f"{PLATFORM_APPLICATIONS}/{application_id}")
    approve = tenant_admin.post(f"{PLATFORM_APPLICATIONS}/{application_id}/approve", json={})
    settings = tenant_admin.patch(SETTINGS_PATH, json={"require_approval": False})

    assert (detail.status_code, approve.status_code, settings.status_code) == (403, 403, 403)
    assert "课题组报销票据整理" not in detail.text


def test_platform_endpoints_require_login(app):
    anonymous = TestClient(app)

    assert anonymous.get(PLATFORM_APPLICATIONS).status_code == 401
    assert anonymous.get("/api/referrals/me").status_code == 401


def test_public_endpoints_need_no_login(app):
    anonymous = TestClient(app)

    assert anonymous.post(APPLICATIONS, json=apply_body()).status_code == 200
    assert anonymous.get(REGISTER, params={"code": "x"}).status_code == 404


@pytest.fixture
def single_admin(admin_client):
    """单账套部署、已登录的管理员。"""
    return admin_client


SINGLE_ENTRIES = (
    ("post", APPLICATIONS, apply_body()),
    ("get", "/api/signup/referral/ABCDEFGH", None),
    ("get", f"{REGISTER}?code=abc", None),
    ("post", REGISTER, {"code": "a", "email": "a@b.cn", "username": "abc", "password": "x" * 8}),
    ("get", "/api/referrals/me", None),
    ("post", "/api/referrals/me/reset", None),
    ("get", PLATFORM_APPLICATIONS, None),
    ("get", f"{PLATFORM_APPLICATIONS}/1", None),
    ("post", f"{PLATFORM_APPLICATIONS}/1/approve", {}),
    ("post", f"{PLATFORM_APPLICATIONS}/1/reject", {}),
    ("post", f"{PLATFORM_APPLICATIONS}/1/resend", None),
    ("get", "/api/platform/referrals", None),
    ("patch", "/api/platform/referrers/1", {"is_disabled": True}),
    ("get", SETTINGS_PATH, None),
    ("patch", SETTINGS_PATH, {"require_approval": False}),
)


@pytest.mark.parametrize("method,path,body", SINGLE_ENTRIES)
def test_single_tenant_hides_every_entry(single_admin, method, path, body):
    kwargs = {"json": body} if body is not None else {}

    response = getattr(single_admin, method)(path, **kwargs)

    assert response.status_code == 404, (path, response.text)


def test_single_tenant_public_entry_is_404_without_login(auth_client):
    setup_password(auth_client)
    anonymous = TestClient(auth_client.app)

    response = anonymous.post(APPLICATIONS, json=apply_body())

    assert response.status_code == 404
    assert response.json()["error"] == "当前部署未开放注册申请"
