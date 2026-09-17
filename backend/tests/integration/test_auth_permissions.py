"""权限：普通用户访问管理员端点 403、业务端点正常；关闭认证时管理员端点放行。"""

import pytest

from tests.auth_helpers import create_user, logged_in_client

ADMIN_ENDPOINTS = [
    ("put", "/api/settings", {"overdue_days": 30}),
    ("post", "/api/backup", None),
    ("post", "/api/categories", {"name": "新分类"}),
    ("patch", "/api/categories/1", {"name": "改名"}),
    ("delete", "/api/categories/1", None),
    ("post", "/api/checklist-rules", {"attachment_kind": "invoice"}),
    ("patch", "/api/checklist-rules/1", {"hint": "x"}),
    ("delete", "/api/checklist-rules/1", None),
    ("get", "/api/users", None),
    ("post", "/api/users", {"username": "hacker", "password": "hacker-pass", "role": "admin"}),
    ("patch", "/api/users/1", {"role": "member"}),
    ("post", "/api/users/1/password", {"password": "hacked-pass-1"}),
]


def call(client, method: str, path: str, body):
    kwargs = {"json": body} if body is not None else {}
    return client.request(method.upper(), path, **kwargs)


@pytest.fixture
def member(auth_app, admin_client):
    create_user(admin_client, "member1")
    return logged_in_client(auth_app, "member1")


@pytest.mark.parametrize(("method", "path", "body"), ADMIN_ENDPOINTS)
def test_member_forbidden_on_admin_endpoints(member, method, path, body):
    response = call(member, method, path, body)
    assert response.status_code == 403
    assert response.json() == {"ok": False, "data": None, "error": "需要管理员权限"}


def test_member_forbidden_even_with_invalid_body(member):
    response = member.post("/api/categories", json={"unknown": 1})
    assert response.status_code == 403


@pytest.mark.parametrize(
    "path",
    ["/api/settings", "/api/categories", "/api/checklist-rules", "/api/projects", "/api/batches"],
)
def test_member_can_read(member, path):
    assert member.get(path).status_code == 200


def test_member_can_use_business_endpoints(member):
    expense = {"spent_on": "2026-09-01", "amount_cents": 1000, "merchant": "文具店"}
    assert member.post("/api/expenses", json=expense).status_code == 200
    assert member.post("/api/projects", json={"name": "课题A"}).status_code == 200
    assert member.post("/api/batches", json={"name": "九月"}).status_code == 200


def test_admin_allowed_on_admin_endpoints(admin_client):
    assert admin_client.put("/api/settings", json={"overdue_days": 30}).status_code == 200
    assert admin_client.post("/api/categories", json={"name": "新分类"}).status_code == 200
    assert admin_client.post("/api/backup").status_code == 200


def test_auth_disabled_allows_admin_endpoints_and_null_users(client):
    assert client.put("/api/settings", json={"overdue_days": 30}).status_code == 200
    assert client.post("/api/categories", json={"name": "新分类"}).status_code == 200
    assert client.get("/api/users").status_code == 200
    body = {"spent_on": "2026-09-01", "amount_cents": 1000, "merchant": "文具店"}
    detail = client.post("/api/expenses", json=body).json()["data"]
    assert detail["created_by"] is None
    assert [event["actor"] for event in detail["timeline"]] == [None]
    batch = client.post("/api/batches", json={"name": "九月"}).json()["data"]
    assert batch["created_by"] is None
