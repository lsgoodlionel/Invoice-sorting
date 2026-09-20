"""跨账套越权红线：平台接口一律只认平台管理员。

覆盖每一个平台接口：普通成员、账套管理员访问都必须 403，
且账套管理员不能借平台路径操作自己的账套（那是运营能力，不是租户能力）。
"""

import pytest
from fastapi.testclient import TestClient

from tests.platform_helpers import login_platform, platform_app, tenant_body
from tests.tenancy_helpers import add_member, host_headers, login_at

# (方法, 路径, 请求体)
PLATFORM_ENDPOINTS = [
    ("get", "/api/platform/overview", None),
    ("get", "/api/platform/tenants", None),
    ("post", "/api/platform/tenants", tenant_body("gamma")),
    ("get", "/api/platform/tenants/alpha", None),
    ("patch", "/api/platform/tenants/alpha", {"name": "改名"}),
    ("get", "/api/platform/tenants/alpha/members", None),
    ("post", "/api/platform/tenants/alpha/members", {"username": "new-one"}),
    ("patch", "/api/platform/tenants/alpha/members/1", {"is_active": False}),
    ("post", "/api/platform/tenants/alpha/members/1/password", {"password": "new-pass-1234"}),
    ("get", "/api/platform/tenants/alpha/invites", None),
    ("post", "/api/platform/tenants/alpha/invites", {}),
    ("get", "/api/platform/plans", None),
    ("post", "/api/platform/plans", {"code": "team"}),
    ("patch", "/api/platform/plans/1", {"name": "团队版"}),
    ("delete", "/api/platform/plans/1", None),
    ("get", "/api/platform/licenses", None),
    ("post", "/api/platform/licenses", {"customer_name": "某客户"}),
    ("patch", "/api/platform/licenses/1", {"status": "revoked"}),
    ("post", "/api/platform/licenses/1/unbind", None),
    ("delete", "/api/platform/licenses/1", None),
    ("post", "/api/platform/tenants/beta/export", None),
]


@pytest.fixture
def app(tmp_path):
    return platform_app(tmp_path)


def call(client: TestClient, method: str, path: str, body):
    kwargs = {"json": body} if body is not None else {}
    return getattr(client, method)(path, **kwargs)


@pytest.mark.parametrize(("method", "path", "body"), PLATFORM_ENDPOINTS)
def test_tenant_admin_is_rejected_everywhere(app, method, path, body):
    client = TestClient(app)
    assert login_at(client, "alpha-admin").status_code == 200

    response = call(client, method, path, body)

    assert response.status_code == 403, response.text
    assert "平台管理员" in response.json()["error"]


@pytest.mark.parametrize(("method", "path", "body"), PLATFORM_ENDPOINTS)
def test_anonymous_is_rejected_everywhere(app, method, path, body):
    response = call(TestClient(app), method, path, body)

    assert response.status_code == 401, response.text


def test_plain_member_is_rejected(app):
    add_member(app, "alpha", "alpha-member")
    client = TestClient(app)
    login_at(client, "alpha-member")

    assert client.get("/api/platform/tenants").status_code == 403


def test_tenant_admin_cannot_manage_own_tenant_through_platform_path(app):
    client = TestClient(app)
    login_at(client, "alpha-admin")

    response = client.patch("/api/platform/tenants/alpha", json={"name": "自封的新名字"})

    assert response.status_code == 403
    assert "平台管理员" in response.json()["error"]


def test_platform_admin_works_on_the_bare_domain(app):
    """裸域名（没有账套子域名）访问平台后台不应因解析不到账套而 400/404。"""
    client = login_platform(app)

    response = client.get("/api/platform/tenants")

    assert response.status_code == 200, response.text
    assert {item["slug"] for item in response.json()["data"]["items"]} == {
        "alpha",
        "beta",
        "platform",
    }


def test_platform_admin_works_on_another_tenant_subdomain(app):
    """即使浏览器停在别人的账套子域名上，平台接口照常可用，但业务接口仍然越不过去。"""
    client = login_platform(app)

    assert client.get("/api/platform/tenants", headers=host_headers("alpha")).status_code == 200
    assert client.get("/api/expenses", headers=host_headers("alpha")).status_code == 403


def test_platform_admin_member_role_still_passes(app):
    """平台管理员在所属账套里只是普通成员时，平台接口仍然可用（平台身份是全局的）。"""
    add_member(app, "beta", "ops-member", role="member")
    from tests.platform_helpers import mark_platform_admin

    mark_platform_admin(app, "ops-member")
    client = TestClient(app)
    login_at(client, "ops-member")

    assert client.get("/api/platform/overview").status_code == 200
