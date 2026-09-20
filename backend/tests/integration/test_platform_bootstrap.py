"""SaaS 首次启动：在网页上创建首个平台管理员（安装命令不含任何账号信息）。

覆盖：空库状态、创建并登录、二次创建 409、并发只成功一次、非法用户名 422、限流仍生效。
"""

import threading

import pytest
from fastapi.testclient import TestClient

from invoice_sorting.main import create_app
from invoice_sorting.platform_admin.bootstrap import (
    MSG_PLATFORM_READY,
    PLATFORM_TENANT_NAME,
    PLATFORM_TENANT_SLUG,
)
from tests.conftest import make_saas_settings
from tests.tenancy_helpers import host_headers, open_tenants

PASSWORD = "platform-pass-123"
PLATFORM_BRIEF = {"slug": PLATFORM_TENANT_SLUG, "name": PLATFORM_TENANT_NAME}


@pytest.fixture
def fresh_saas_app(tmp_path):
    """全新的多账套部署：控制库里一个账号、一个账套都没有。"""
    return create_app(make_saas_settings(tmp_path, auth_enabled=True))


@pytest.fixture
def fresh_client(fresh_saas_app) -> TestClient:
    return TestClient(fresh_saas_app)


def setup_platform(client, username: str | None = "ops-boss", password: str = PASSWORD):
    body: dict[str, object] = {"password": password}
    if username is not None:
        body["username"] = username
    return client.post("/api/auth/setup", json=body)


def test_status_asks_for_setup_on_fresh_saas(fresh_client):
    status = fresh_client.get("/api/auth/status").json()["data"]

    assert status == {
        "auth_enabled": True,
        "password_set": False,
        "authenticated": False,
        "user": None,
        "multi_tenant": True,
        "tenant": None,
    }


def test_status_reports_ready_once_an_account_exists(fresh_saas_app, fresh_client):
    setup_platform(fresh_client)
    other = TestClient(fresh_saas_app)

    assert other.get("/api/auth/status").json()["data"]["password_set"] is True


def test_setup_creates_platform_admin_and_logs_in(fresh_saas_app, fresh_client):
    response = setup_platform(fresh_client)

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["authenticated"] is True
    assert data["user"]["username"] == "ops-boss"
    assert data["user"]["role"] == "admin"
    assert data["tenant"] == PLATFORM_BRIEF
    assert fresh_client.get("/api/platform/overview").status_code == 200


def test_setup_marks_platform_admin_in_control_db(fresh_saas_app, fresh_client):
    setup_platform(fresh_client, "ops-boss")

    from invoice_sorting.control.repository import find_account, find_tenant

    with fresh_saas_app.state.control_session_factory() as control:
        account = find_account(control, "ops-boss")
        tenant = find_tenant(control, PLATFORM_TENANT_SLUG)
        assert account is not None and account.is_platform_admin is True
        assert account.password_hash and PASSWORD not in account.password_hash
        assert tenant is not None and tenant.name == PLATFORM_TENANT_NAME


def test_setup_defaults_username_to_admin(fresh_client):
    response = setup_platform(fresh_client, username=None)

    assert response.status_code == 200, response.text
    assert response.json()["data"]["user"]["username"] == "admin"


def test_setup_normalizes_username(fresh_client):
    response = setup_platform(fresh_client, "  OPS-Boss  ")

    assert response.status_code == 200, response.text
    assert response.json()["data"]["user"]["username"] == "ops-boss"


def test_created_admin_can_log_in_again(fresh_saas_app, fresh_client):
    setup_platform(fresh_client)
    other = TestClient(fresh_saas_app)

    response = other.post("/api/auth/login", json={"username": "ops-boss", "password": PASSWORD})

    assert response.status_code == 200, response.text
    assert response.json()["data"]["tenant"] == PLATFORM_BRIEF
    assert other.get("/api/platform/overview").status_code == 200


def test_second_setup_conflicts(fresh_saas_app, fresh_client):
    setup_platform(fresh_client)
    other = TestClient(fresh_saas_app)

    response = setup_platform(other, "someone-else")

    assert response.status_code == 409
    assert response.json()["error"] == MSG_PLATFORM_READY
    assert "set-cookie" not in response.headers


def test_setup_rejected_when_any_account_exists(fresh_saas_app, fresh_client):
    """命令行已开通过平台管理员：网页不能再抢注。"""
    open_tenants(fresh_saas_app, "alpha")
    from tests.tenancy_helpers import add_member

    add_member(fresh_saas_app, "alpha", "alpha-admin", role="admin")

    response = setup_platform(fresh_client)

    assert response.status_code == 409
    assert response.json()["error"] == MSG_PLATFORM_READY


def test_setup_rejected_when_platform_tenant_exists(fresh_saas_app, fresh_client):
    open_tenants(fresh_saas_app, PLATFORM_TENANT_SLUG)

    assert setup_platform(fresh_client).status_code == 409


@pytest.mark.parametrize("username", ["ab", "x" * 33, "bad user", "坏账号", ""])
def test_setup_rejects_invalid_username(fresh_client, username):
    response = setup_platform(fresh_client, username)

    assert response.status_code == 422
    assert "用户名" in response.json()["error"]


def test_setup_rejects_non_string_username(fresh_client):
    assert (
        fresh_client.post(
            "/api/auth/setup", json={"username": 123, "password": PASSWORD}
        ).status_code
        == 422
    )


@pytest.mark.parametrize("password", ["short", "x" * 129])
def test_setup_rejects_invalid_password(fresh_client, password):
    response = setup_platform(fresh_client, password=password)

    assert response.status_code == 422
    assert "8–128" in response.json()["error"]


def test_concurrent_setup_only_one_succeeds(fresh_saas_app):
    barrier = threading.Barrier(4)
    results: list[int] = []

    def attempt(index: int) -> None:
        client = TestClient(fresh_saas_app)
        barrier.wait()
        results.append(setup_platform(client, f"ops-{index}").status_code)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == [200, 409, 409, 409]
    from sqlalchemy import select

    from invoice_sorting.control.models import Account

    with fresh_saas_app.state.control_session_factory() as control:
        assert len(list(control.scalars(select(Account)))) == 1


def test_login_rate_limit_still_applies_after_setup(fresh_saas_app, fresh_client):
    setup_platform(fresh_client)
    other = TestClient(fresh_saas_app)
    for _ in range(5):
        wrong = {"username": "ops-boss", "password": "wrong-password"}
        assert other.post("/api/auth/login", json=wrong).status_code == 401

    response = other.post("/api/auth/login", json={"username": "ops-boss", "password": PASSWORD})

    assert response.status_code == 429
    assert "尝试次数过多" in response.json()["error"]


def test_setup_on_unknown_subdomain_still_reports_missing_tenant(fresh_client):
    """带账套子域名访问的请求照旧按账套解析；全新部署下该账套不存在。"""
    response = fresh_client.post(
        "/api/auth/setup", json={"password": PASSWORD}, headers=host_headers("alpha")
    )

    assert response.status_code == 404
    assert response.json()["error"] == "账套不存在"
