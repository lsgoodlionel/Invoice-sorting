"""任意账套的成员管理与邀请码：添加、停用、重置密码，且镜像同步到该账套业务库。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from invoice_sorting.db.models import User
from tests.platform_helpers import login_platform, platform_app
from tests.tenancy_helpers import add_member, host_headers, login_at

MEMBERS = "/api/platform/tenants/{slug}/members"
NEW_PASSWORD = "brand-new-pass-1"


@pytest.fixture
def app(tmp_path):
    return platform_app(tmp_path)


@pytest.fixture
def client(app):
    return login_platform(app)


def mirror_usernames(app, slug: str) -> set[str]:
    context = app.state.tenants.get(slug)
    with context.session_factory() as business:
        return {user.username for user in business.scalars(select(User))}


def test_add_member_to_another_tenant(app, client):
    body = {"username": "zhaoliu", "display_name": "赵六", "password": NEW_PASSWORD}

    response = client.post(MEMBERS.format(slug="beta"), json=body)

    assert response.status_code == 200, response.text
    assert response.json()["data"]["display_name"] == "赵六"
    assert "zhaoliu" in mirror_usernames(app, "beta")
    assert login_at(TestClient(app), "zhaoliu", NEW_PASSWORD, slug="beta").status_code == 200


def test_new_account_requires_a_password(client):
    response = client.post(MEMBERS.format(slug="beta"), json={"username": "nopass"})

    assert response.status_code == 400
    assert "初始密码" in response.json()["error"]


def test_existing_account_joins_without_touching_its_password(app, client):
    add_member(app, "alpha", "shared-user")

    response = client.post(MEMBERS.format(slug="beta"), json={"username": "shared-user"})

    assert response.status_code == 200, response.text
    assert login_at(TestClient(app), "shared-user", slug="beta").status_code == 200


def test_duplicate_member_is_rejected(client):
    response = client.post(MEMBERS.format(slug="alpha"), json={"username": "alpha-admin"})

    assert response.status_code == 409


def test_list_members_of_any_tenant(client):
    data = client.get(MEMBERS.format(slug="beta")).json()["data"]

    assert [member["username"] for member in data] == ["beta-admin"]


def test_deactivate_member_kills_their_sessions(app, client):
    add_member(app, "beta", "temp-user")
    member = TestClient(app)
    assert login_at(member, "temp-user", slug="beta").status_code == 200
    status = member.get("/api/auth/status", headers=host_headers("beta")).json()
    account_id = status["data"]["user"]["id"]

    path = f"{MEMBERS.format(slug='beta')}/{account_id}"
    assert client.patch(path, json={"is_active": False}).status_code == 200

    assert member.get("/api/expenses", headers=host_headers("beta")).status_code == 401


def test_last_admin_cannot_be_removed(client):
    data = client.get(MEMBERS.format(slug="beta")).json()["data"]
    path = f"{MEMBERS.format(slug='beta')}/{data[0]['id']}"

    response = client.patch(path, json={"is_active": False})

    assert response.status_code == 400 and "管理员" in response.json()["error"]


def test_reset_password_of_any_tenant_member(app, client):
    data = client.get(MEMBERS.format(slug="beta")).json()["data"]
    path = f"{MEMBERS.format(slug='beta')}/{data[0]['id']}/password"

    assert client.post(path, json={"password": NEW_PASSWORD}).status_code == 200

    assert login_at(TestClient(app), "beta-admin", NEW_PASSWORD, slug="beta").status_code == 200


def test_member_of_another_tenant_is_not_found(app, client):
    data = client.get(MEMBERS.format(slug="alpha")).json()["data"]
    path = f"{MEMBERS.format(slug='beta')}/{data[0]['id']}"

    assert client.patch(path, json={"is_active": False}).status_code == 404


def test_issue_and_list_invites_for_any_tenant(client):
    created = client.post("/api/platform/tenants/beta/invites", json={"role": "admin"})

    assert created.status_code == 200, created.text
    code = created.json()["data"]["code"]
    listed = client.get("/api/platform/tenants/beta/invites").json()["data"]
    assert [invite["code"] for invite in listed] == [code]
    assert listed[0]["role"] == "admin" and listed[0]["is_used"] is False


def test_issued_invite_can_be_redeemed(app, client):
    code = client.post("/api/platform/tenants/beta/invites", json={}).json()["data"]["code"]
    body = {"code": code, "username": "invited", "password": NEW_PASSWORD}

    response = TestClient(app).post("/api/auth/join", json=body)

    assert response.status_code == 200, response.text
    assert response.json()["data"]["user"]["username"] == "invited"
