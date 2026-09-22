"""多账套下的删除成员：账套管理员“移出本账套”，平台后台可对任意账套操作。

测试数据全部虚构：账号名、姓名与密码都是编造的，不对应任何真实人员。
"""

import pytest
from fastapi.testclient import TestClient

from invoice_sorting.control.models import Account
from invoice_sorting.db.models import User
from tests.platform_helpers import login_platform, platform_app
from tests.tenancy_helpers import add_member, host_headers, login_at

MEMBERS = "/api/platform/tenants/{slug}/members"


@pytest.fixture
def app(tmp_path):
    return platform_app(tmp_path)


def mirror(app, slug: str, account_id: int) -> User | None:
    with app.state.tenants.get(slug).session_factory() as business:
        return business.get(User, account_id)


def enter(app, slug: str, username: str) -> TestClient:
    """登录一次，让该账套业务库补齐此人的镜像。"""
    client = TestClient(app)
    assert login_at(client, username, slug=slug).status_code == 200
    return client


def test_tenant_admin_removes_member_from_own_tenant_only(app):
    shared = add_member(app, "alpha", "shared-user", display_name="虚构戊")
    add_member(app, "beta", "shared-user")
    enter(app, "alpha", "shared-user")
    admin = enter(app, "alpha", "alpha-admin")

    response = admin.delete(f"/api/users/{shared}", headers=host_headers("alpha"))

    assert response.status_code == 200, response.text
    assert response.json()["data"]["is_account_removed"] is False
    listed = admin.get("/api/users", headers=host_headers("alpha")).json()["data"]
    assert [user["username"] for user in listed] == ["alpha-admin"]
    assert login_at(TestClient(app), "shared-user", slug="alpha").status_code != 200
    assert login_at(TestClient(app), "shared-user", slug="beta").status_code == 200
    assert mirror(app, "alpha", shared).is_deleted
    assert mirror(app, "alpha", shared).display_name == "虚构戊"


def test_tenant_admin_cannot_delete_member_of_another_tenant(app):
    outsider = add_member(app, "beta", "beta-only")
    admin = enter(app, "alpha", "alpha-admin")

    response = admin.delete(f"/api/users/{outsider}", headers=host_headers("alpha"))

    assert response.status_code == 404
    assert login_at(TestClient(app), "beta-only", slug="beta").status_code == 200


def test_platform_admin_deletes_member_of_any_tenant(app):
    member = add_member(app, "beta", "beta-member", display_name="虚构己")
    enter(app, "beta", "beta-member")

    response = login_platform(app).delete(f"{MEMBERS.format(slug='beta')}/{member}")

    assert response.status_code == 200, response.text
    assert response.json()["data"]["is_account_removed"] is True
    with app.state.control_session_factory() as control:
        assert control.get(Account, member) is None
    assert mirror(app, "beta", member).is_deleted
    assert login_at(TestClient(app), "beta-member", slug="beta").status_code != 200


def test_platform_delete_keeps_last_admin_and_reports_missing(app):
    platform = login_platform(app)
    admin_id = platform.get(MEMBERS.format(slug="beta")).json()["data"][0]["id"]

    last = platform.delete(f"{MEMBERS.format(slug='beta')}/{admin_id}")
    missing = platform.delete(f"{MEMBERS.format(slug='beta')}/99999")

    assert last.status_code == 409 and "最后一名可用的管理员" in last.json()["error"]
    assert missing.status_code == 404
    assert login_at(TestClient(app), "beta-admin", slug="beta").status_code == 200


def test_tenant_admin_cannot_use_platform_delete(app):
    member = add_member(app, "beta", "beta-member")
    admin = enter(app, "beta", "beta-admin")

    response = admin.delete(f"{MEMBERS.format(slug='beta')}/{member}")

    assert response.status_code == 403


def test_member_added_back_gets_a_live_mirror_again(app):
    shared = add_member(app, "alpha", "shared-user")
    add_member(app, "beta", "shared-user")
    enter(app, "alpha", "shared-user")
    platform = login_platform(app)
    platform.delete(f"{MEMBERS.format(slug='alpha')}/{shared}")

    added = platform.post(MEMBERS.format(slug="alpha"), json={"username": "shared-user"})

    assert added.status_code == 200, added.text
    assert not mirror(app, "alpha", shared).is_deleted
    assert login_at(TestClient(app), "shared-user", slug="alpha").status_code == 200
