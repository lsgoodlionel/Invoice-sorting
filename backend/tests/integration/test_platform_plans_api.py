"""套餐管理：增删改查；被账套引用的套餐不能删除。

控制库启动时已内置一个免费套餐，因此断言都只看本用例自己建的那一条。
"""

import pytest

from tests.platform_helpers import login_platform, platform_app

PLANS = "/api/platform/plans"


@pytest.fixture
def client(tmp_path):
    return login_platform(platform_app(tmp_path))


def create(client, code: str = "team", **overrides) -> dict:
    body = {"code": code, "name": "团队版", "max_users": 5, "max_storage_mb": 1024, **overrides}
    response = client.post(PLANS, json=body)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def codes(client) -> list[str]:
    return [plan["code"] for plan in client.get(PLANS).json()["data"]]


def find(client, code: str) -> dict:
    return next(plan for plan in client.get(PLANS).json()["data"] if plan["code"] == code)


def test_create_and_list_plans(client):
    create(client, max_expenses_per_month=500, features={"export": True})

    plan = find(client, "team")

    assert plan["max_users"] == 5 and plan["max_storage_mb"] == 1024
    assert plan["max_expenses_per_month"] == 500
    assert plan["features"] == {"export": True}


def test_zero_means_unlimited_and_is_the_default(client):
    plan = create(client, code="solo", max_users=0, max_storage_mb=0)

    assert plan["max_users"] == 0 and plan["max_expenses_per_month"] == 0


def test_duplicate_code_is_rejected(client):
    create(client)

    assert client.post(PLANS, json={"code": "TEAM"}).status_code == 409


def test_negative_quota_is_rejected(client):
    assert client.post(PLANS, json={"code": "bad", "max_users": -1}).status_code == 422


def test_update_plan_limits(client):
    plan = create(client)

    data = client.patch(f"{PLANS}/{plan['id']}", json={"max_users": 20}).json()["data"]

    assert data["max_users"] == 20 and data["max_storage_mb"] == 1024


def test_delete_unused_plan(client):
    plan = create(client)

    assert client.delete(f"{PLANS}/{plan['id']}").status_code == 200
    assert "team" not in codes(client)


def test_plan_in_use_cannot_be_deleted(client):
    plan = create(client)
    client.patch("/api/platform/tenants/alpha", json={"plan_code": "team"})

    response = client.delete(f"{PLANS}/{plan['id']}")

    assert response.status_code == 409
    assert "1 个账套" in response.json()["error"]


def test_unknown_plan_is_404(client):
    assert client.patch(f"{PLANS}/999", json={"name": "无"}).status_code == 404
