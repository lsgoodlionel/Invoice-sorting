"""账套管理：列表与搜索分页、开通、改套餐与到期日、停用恢复与关闭。"""

import pytest
from fastapi.testclient import TestClient

from invoice_sorting.control.repository import find_tenant
from tests.platform_helpers import login_platform, platform_app, tenant_body
from tests.tenancy_helpers import host_headers, login_at

TENANTS = "/api/platform/tenants"


@pytest.fixture
def app(tmp_path):
    return platform_app(tmp_path)


@pytest.fixture
def client(app):
    return login_platform(app)


def make_plan(client, code: str = "team", **limits) -> dict:
    body = {"code": code, "name": "团队版", **limits}
    response = client.post("/api/platform/plans", json=body)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_list_shows_plan_members_and_creation_time(client):
    make_plan(client, max_users=5)
    client.patch(f"{TENANTS}/alpha", json={"plan_code": "team"})

    data = client.get(TENANTS).json()["data"]
    alpha = next(item for item in data["items"] if item["slug"] == "alpha")

    assert alpha["plan"] == {"code": "team", "name": "团队版"}
    assert alpha["member_count"] == 1
    assert alpha["status"] == "active"
    assert alpha["created_at"] and data["total"] == 3


def test_list_supports_search_and_paging(client):
    response = client.get(TENANTS, params={"q": "alpha", "page": 1, "page_size": 1})

    data = response.json()["data"]
    assert [item["slug"] for item in data["items"]] == ["alpha"]
    assert data["total"] == 1 and data["page_size"] == 1


def test_open_tenant_with_first_admin(app, client):
    response = client.post(TENANTS, json=tenant_body("gamma", plan_code=None))

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["slug"] == "gamma" and data["admin"]["username"] == "gamma-boss"
    assert data["admin"]["role"] == "admin" and data["invite"] is None
    assert login_at(TestClient(app), "gamma-boss").status_code == 200


def test_open_tenant_with_invite_instead_of_admin(client):
    body = {"slug": "delta", "name": "德尔塔账套", "with_invite": True}

    data = client.post(TENANTS, json=body).json()["data"]

    assert data["admin"] is None
    assert data["invite"]["role"] == "admin" and data["invite"]["code"]


def test_open_tenant_requires_admin_or_invite(client):
    response = client.post(TENANTS, json={"slug": "delta"})

    assert response.status_code == 400
    assert "邀请码" in response.json()["error"]


def test_duplicate_slug_is_rejected(client):
    assert client.post(TENANTS, json=tenant_body("alpha")).status_code == 409


def test_bad_slug_is_rejected(client):
    assert client.post(TENANTS, json=tenant_body("../etc")).status_code == 422


def test_change_name_plan_and_expiry(client):
    make_plan(client)
    body = {"name": "阿尔法有限公司", "plan_code": "team", "expires_on": "2027-01-31"}

    data = client.patch(f"{TENANTS}/alpha", json=body).json()["data"]

    assert data["name"] == "阿尔法有限公司"
    assert data["plan"]["code"] == "team" and data["expires_on"] == "2027-01-31"


def test_expiry_can_be_cleared_to_permanent(client):
    client.patch(f"{TENANTS}/alpha", json={"expires_on": "2027-01-31"})

    data = client.patch(f"{TENANTS}/alpha", json={"expires_on": None}).json()["data"]

    assert data["expires_on"] is None


def test_unknown_plan_code_is_rejected(client):
    response = client.patch(f"{TENANTS}/alpha", json={"plan_code": "nope"})

    assert response.status_code == 404 and "套餐" in response.json()["error"]


def test_suspend_releases_the_tenant_runtime(app, client):
    client.get("/api/platform/tenants/alpha")  # 先让账套进入缓存
    app.state.tenants.get("alpha")
    assert "alpha" in app.state.tenants.cached_slugs()

    data = client.patch(f"{TENANTS}/alpha", json={"status": "suspended"}).json()["data"]

    assert data["status"] == "suspended"
    assert "alpha" not in app.state.tenants.cached_slugs()


def test_suspended_tenant_members_cannot_log_in(app, client):
    client.patch(f"{TENANTS}/alpha", json={"status": "suspended"})

    assert login_at(TestClient(app), "alpha-admin", slug="alpha").status_code == 401


def test_restore_makes_the_tenant_usable_again(app, client):
    client.patch(f"{TENANTS}/alpha", json={"status": "suspended"})

    client.patch(f"{TENANTS}/alpha", json={"status": "active"})

    assert login_at(TestClient(app), "alpha-admin", slug="alpha").status_code == 200


def test_close_keeps_the_row_but_stops_service(app, client):
    client.patch(f"{TENANTS}/beta", json={"status": "closed"})

    with app.state.control_session_factory() as control:
        assert find_tenant(control, "beta") is not None
    member = TestClient(app)
    assert login_at(member, "beta-admin", slug="beta").status_code == 401


def test_unknown_tenant_is_404(client):
    assert client.get(f"{TENANTS}/nope").status_code == 404


def test_detail_is_readable_from_any_subdomain(client):
    response = client.get(f"{TENANTS}/beta", headers=host_headers("alpha"))

    assert response.status_code == 200
    assert response.json()["data"]["slug"] == "beta"
