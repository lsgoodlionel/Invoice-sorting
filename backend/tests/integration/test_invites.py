"""邀请码：管理员生成、受邀人加入、各类无效邀请码，以及只能管自己账套。"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from invoice_sorting.db.models import now
from invoice_sorting.main import create_app
from tests.auth_helpers import MEMBER_PASSWORD, create_user, logged_in_client
from tests.conftest import make_saas_settings
from tests.tenancy_helpers import add_member, host_headers, login_at, open_tenants

JOIN_PASSWORD = "joiner-pass-123"


def make_invite(client, role: str = "member", headers: dict | None = None) -> dict:
    response = client.post("/api/invites", json={"role": role}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def join(client, code: str, username: str, password: str = JOIN_PASSWORD, **extra):
    body = {"code": code, "username": username, "password": password, **extra}
    return client.post("/api/auth/join", json=body)


def test_admin_creates_and_lists_invite(admin_client):
    invite = make_invite(admin_client, role="admin")

    assert set(invite) == {"id", "code", "role", "expires_on", "is_used", "used_at", "created_at"}
    assert invite["role"] == "admin" and invite["is_used"] is False
    assert invite["expires_on"] == (now().date() + timedelta(days=7)).isoformat()
    listed = admin_client.get("/api/invites").json()["data"]
    assert [row["code"] for row in listed] == [invite["code"]]


def test_new_user_joins_with_invite_and_is_logged_in(auth_app, admin_client):
    invite = make_invite(admin_client)
    client = TestClient(auth_app)

    response = join(client, invite["code"], "zhaoliu", display_name="赵六")

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["authenticated"] is True
    assert data["user"]["display_name"] == "赵六" and data["user"]["role"] == "member"
    assert client.get("/api/expenses").status_code == 200
    usernames = [row["username"] for row in admin_client.get("/api/users").json()["data"]]
    assert usernames == ["admin", "zhaoliu"]
    assert admin_client.get("/api/invites").json()["data"][0]["is_used"] is True


def test_joined_user_appears_as_operator(auth_app, admin_client):
    invite = make_invite(admin_client)
    client = TestClient(auth_app)
    join(client, invite["code"], "zhaoliu", display_name="赵六")

    body = {"spent_on": "2026-09-01", "amount_cents": 1000, "merchant": "文具店"}
    created = client.post("/api/expenses", json=body).json()["data"]

    assert created["created_by"]["display_name"] == "赵六"


def test_used_invite_is_rejected(auth_app, admin_client):
    invite = make_invite(admin_client)
    join(TestClient(auth_app), invite["code"], "zhaoliu")

    response = join(TestClient(auth_app), invite["code"], "sunqi")

    assert response.status_code == 409
    assert response.json()["error"] == "邀请码已被使用，请向管理员重新索取"


def test_expired_invite_is_rejected(auth_app, admin_client):
    yesterday = (now().date() - timedelta(days=1)).isoformat()
    created = admin_client.post("/api/invites", json={"role": "member", "expires_on": yesterday})

    response = join(TestClient(auth_app), created.json()["data"]["code"], "zhaoliu")

    assert response.status_code == 410
    assert response.json()["error"] == "邀请码已过期，请向管理员重新索取"


def test_unknown_invite_is_rejected(auth_app, admin_client):
    response = join(TestClient(auth_app), "not-a-real-code", "zhaoliu")

    assert response.status_code == 404
    assert response.json()["error"] == "邀请码无效，请向管理员重新索取"


def test_existing_account_must_prove_its_password(auth_app, admin_client):
    create_user(admin_client, "lisi")
    invite = make_invite(admin_client)

    wrong = join(TestClient(auth_app), invite["code"], "lisi", password="wrong-pass-123")

    assert wrong.status_code == 401
    assert wrong.json()["error"] == "该用户名已存在，请填写它的登录密码"


def test_existing_member_cannot_join_twice(auth_app, admin_client):
    create_user(admin_client, "lisi")
    invite = make_invite(admin_client)

    response = join(TestClient(auth_app), invite["code"], "lisi", password=MEMBER_PASSWORD)

    assert response.status_code == 409
    assert response.json()["error"] == "该账号已在此账套中，请直接登录"


def test_member_cannot_create_invites(auth_app, admin_client):
    create_user(admin_client, "member1")
    member = logged_in_client(auth_app, "member1")

    assert member.post("/api/invites", json={"role": "admin"}).status_code == 403
    assert member.get("/api/invites").status_code == 403


def test_invite_role_is_validated(admin_client):
    response = admin_client.post("/api/invites", json={"role": "owner"})

    assert response.status_code == 422


@pytest.fixture
def saas_app_with_tenants(tmp_path):
    app = create_app(make_saas_settings(tmp_path, auth_enabled=True))
    open_tenants(app, "alpha", "beta")
    add_member(app, "alpha", "admin1", role="admin")
    add_member(app, "beta", "admin2", role="admin")
    return app


def test_invite_only_covers_its_own_tenant(saas_app_with_tenants):
    """alpha 管理员生成的邀请码把人加进 alpha，且看不到 beta 的邀请码。"""
    app = saas_app_with_tenants
    alpha = TestClient(app)
    login_at(alpha, "admin1", slug="alpha")
    beta = TestClient(app)
    login_at(beta, "admin2", slug="beta")
    make_invite(beta, headers=host_headers("beta"))

    invite = make_invite(alpha, headers=host_headers("alpha"))
    joiner = TestClient(app)
    response = join(joiner, invite["code"], "zhaoliu")

    assert response.status_code == 200, response.text
    assert response.json()["data"]["tenant"] == {"slug": "alpha", "name": "alpha 账套"}
    assert len(alpha.get("/api/invites", headers=host_headers("alpha")).json()["data"]) == 1
    beta_users = beta.get("/api/users", headers=host_headers("beta")).json()["data"]
    assert [row["username"] for row in beta_users] == ["admin2"]


def test_account_can_join_a_second_tenant_with_its_password(saas_app_with_tenants):
    app = saas_app_with_tenants
    beta = TestClient(app)
    login_at(beta, "admin2", slug="beta")
    invite = make_invite(beta, headers=host_headers("beta"))

    joiner = TestClient(app)
    response = join(joiner, invite["code"], "admin1", password="member-pass-123")

    assert response.status_code == 200, response.text
    assert response.json()["data"]["tenant"]["slug"] == "beta"
    tenants = joiner.get("/api/auth/tenants").json()["data"]
    assert sorted(row["slug"] for row in tenants) == ["alpha", "beta"]
