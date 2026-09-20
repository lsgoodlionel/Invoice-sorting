"""套餐额度拦截：成员数、存储、当月新增记录各自拦截并说明超的是哪一项。"""

import io

from tests.quota_helpers import fill_library, set_plan
from tests.tenancy_helpers import host_headers, open_tenants

PAYLOAD = {"spent_on": "2026-09-15", "amount_cents": 1200, "merchant": "阿尔法便利店"}


def create_expense(client, slug: str, merchant: str = "阿尔法便利店"):
    return client.post(
        "/api/expenses", json={**PAYLOAD, "merchant": merchant}, headers=host_headers(slug)
    )


def upload(client, slug: str):
    files = {"files": ("发票.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")}
    return client.post("/api/imports", files=files, headers=host_headers(slug))


def add_user(client, slug: str, username: str):
    body = {"username": username, "display_name": username, "password": "member-pass-123"}
    return client.post("/api/users", json=body, headers=host_headers(slug))


def open_tenant(app, slug: str = "alpha", **plan) -> None:
    open_tenants(app, slug)
    set_plan(app, slug, **plan)


def test_monthly_expense_limit_blocks_the_next_record(saas_app, saas_client):
    open_tenant(saas_app, max_expenses_per_month=2)

    assert create_expense(saas_client, "alpha", "第一笔").status_code == 200
    assert create_expense(saas_client, "alpha", "第二笔").status_code == 200
    blocked = create_expense(saas_client, "alpha", "第三笔")

    assert blocked.status_code == 403
    error = blocked.json()["error"]
    assert "本月新增记录" in error and "2 条" in error
    assert "升级套餐" in error


def test_unlimited_plan_never_blocks(saas_app, saas_client):
    open_tenant(saas_app, max_expenses_per_month=0)

    for index in range(4):
        assert create_expense(saas_client, "alpha", f"第{index}笔").status_code == 200


def test_other_tenant_quota_is_counted_separately(saas_app, saas_client):
    open_tenant(saas_app, "alpha", max_expenses_per_month=1)
    open_tenant(saas_app, "beta", max_expenses_per_month=1)
    create_expense(saas_client, "alpha")

    assert create_expense(saas_client, "alpha").status_code == 403
    assert create_expense(saas_client, "beta").status_code == 200


def test_editing_and_deleting_are_allowed_when_the_monthly_cap_is_reached(saas_app, saas_client):
    """额度只拦“新增”，已有记录仍可修改与删除，否则用户无法自救。"""
    open_tenant(saas_app, max_expenses_per_month=1)
    expense_id = create_expense(saas_client, "alpha").json()["data"]["id"]
    headers = host_headers("alpha")

    path = f"/api/expenses/{expense_id}"
    patched = saas_client.patch(path, json={"note": "改一下"}, headers=headers)
    removed = saas_client.delete(path, headers=headers)

    assert (patched.status_code, removed.status_code) == (200, 200)


def test_storage_limit_blocks_uploads(saas_app, saas_client, saas_settings):
    open_tenant(saas_app, max_storage_mb=1)
    saas_client.get("/api/expenses", headers=host_headers("alpha"))  # 建库建目录
    fill_library(saas_settings, "alpha", megabytes=2)

    blocked = upload(saas_client, "alpha")

    assert blocked.status_code == 403
    error = blocked.json()["error"]
    assert "存储空间" in error and "1 MB" in error
    assert "清理" in error


def test_upload_is_allowed_below_the_storage_limit(saas_app, saas_client):
    open_tenant(saas_app, max_storage_mb=50)

    assert upload(saas_client, "alpha").status_code == 200


def test_member_limit_blocks_adding_users(saas_app, saas_client):
    open_tenant(saas_app, max_users=1)
    assert add_user(saas_client, "alpha", "zhang").status_code == 200

    blocked = add_user(saas_client, "alpha", "li")

    assert blocked.status_code == 403
    error = blocked.json()["error"]
    assert "成员数量" in error and "1 人" in error


def test_member_limit_also_blocks_joining_with_an_invite(saas_app, saas_client):
    """邀请码加入走公开端点，不经过写守卫，必须单独校验用户数。"""
    open_tenant(saas_app, max_users=1)
    headers = host_headers("alpha")
    add_user(saas_client, "alpha", "zhang")
    invite = saas_client.post("/api/invites", json={"role": "member"}, headers=headers)
    code = invite.json()["data"]["code"]

    blocked = saas_client.post(
        "/api/auth/join",
        json={"code": code, "username": "wang", "password": "member-pass-123"},
        headers=headers,
    )

    assert blocked.status_code == 403
    assert "成员数量" in blocked.json()["error"]


def test_single_tenant_deployment_is_not_limited(app, client):
    """单账套私有化部署没有套餐概念：即使控制库里有套餐也不生效。"""
    set_plan(app, "default", max_expenses_per_month=1, max_users=1, max_storage_mb=1)

    for index in range(3):
        response = client.post("/api/expenses", json={**PAYLOAD, "merchant": f"第{index}笔"})
        assert response.status_code == 200, response.text
