"""租户内用户镜像：业务库 app_user 跟随控制面账号 + 成员关系，且不再使用其 password_hash。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from invoice_sorting.db.models import User
from invoice_sorting.main import create_app
from tests.auth_helpers import create_user, logged_in_client
from tests.conftest import make_saas_settings
from tests.tenancy_helpers import add_member, host_headers, login_at, open_tenants


def mirror_rows(app, slug: str | None = None) -> list[User]:
    factory = app.state.tenants.get(slug).session_factory if slug else app.state.session_factory
    with factory() as db:
        return list(db.scalars(select(User).order_by(User.id)))


def test_created_member_is_mirrored_without_password(auth_app, admin_client):
    created = create_user(admin_client, "zhangsan", display_name="张三", role="admin")

    rows = {row.id: row for row in mirror_rows(auth_app)}

    mirrored = rows[created["id"]]
    assert (mirrored.username, mirrored.display_name) == ("zhangsan", "张三")
    assert mirrored.role == "admin" and mirrored.is_active is True
    assert mirrored.password_hash is None  # 密码只存在控制库


def test_rename_and_role_change_reach_the_mirror(auth_app, admin_client):
    created = create_user(admin_client, "lisi")

    admin_client.patch(
        f"/api/users/{created['id']}", json={"display_name": "李四", "role": "admin"}
    )

    mirrored = {row.id: row for row in mirror_rows(auth_app)}[created["id"]]
    assert (mirrored.display_name, mirrored.role) == ("李四", "admin")


def test_deactivation_reaches_the_mirror(auth_app, admin_client):
    created = create_user(admin_client, "wangwu")

    admin_client.patch(f"/api/users/{created['id']}", json={"is_active": False})

    mirrored = {row.id: row for row in mirror_rows(auth_app)}[created["id"]]
    assert mirrored.is_active is False


def test_mirror_keeps_operator_names(auth_app, admin_client):
    create_user(admin_client, "zhouba", display_name="周八")
    member = logged_in_client(auth_app, "zhouba")

    body = {"spent_on": "2026-09-01", "amount_cents": 1000, "merchant": "文具店"}
    detail = member.post("/api/expenses", json=body).json()["data"]

    assert detail["created_by"]["display_name"] == "周八"
    assert [event["actor"]["display_name"] for event in detail["timeline"]] == ["周八"]


@pytest.fixture
def saas_app(tmp_path):
    app = create_app(make_saas_settings(tmp_path, auth_enabled=True))
    open_tenants(app, "alpha", "beta")
    return app


def test_tenant_business_db_gets_mirrors_on_first_load(saas_app):
    """控制库先有成员，租户业务库首次加载时按 membership 补齐镜像。"""
    add_member(saas_app, "alpha", "zhangsan", role="admin", display_name="张三")
    add_member(saas_app, "alpha", "lisi")
    client = TestClient(saas_app)

    assert login_at(client, "zhangsan").status_code == 200

    rows = mirror_rows(saas_app, "alpha")
    assert [(row.username, row.role) for row in rows] == [("zhangsan", "admin"), ("lisi", "member")]
    assert all(row.password_hash is None for row in rows)
    listed = client.get("/api/users", headers=host_headers("alpha")).json()["data"]
    assert [row["username"] for row in listed] == ["zhangsan", "lisi"]


def test_saas_tenant_has_no_stray_admin_mirror(saas_app):
    """SaaS 租户成员由控制面开通，业务库不预置 admin 镜像（否则 id 会与别的账号撞车）。"""
    add_member(saas_app, "beta", "lisi", role="admin")
    client = TestClient(saas_app)
    login_at(client, "lisi", slug="beta")

    assert [row.username for row in mirror_rows(saas_app, "beta")] == ["lisi"]


def test_mirror_ids_match_control_account_ids(saas_app):
    account_id = add_member(saas_app, "alpha", "zhangsan", role="admin")
    client = TestClient(saas_app)
    login_at(client, "zhangsan")

    assert [row.id for row in mirror_rows(saas_app, "alpha")] == [account_id]
