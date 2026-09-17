"""设置、分类、经费项目、清单规则、备份 API。"""

from pathlib import Path

import pytest


def data(response):
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    return body["data"]


def test_settings_get_and_put(client, settings):
    current = data(client.get("/api/settings"))
    assert current == {
        "buyer_name": "",
        "buyer_tax_id": "",
        "overdue_days": 30,
        "local_region": "上海",
        "detail_platforms": ["京东", "当当", "圆迈"],
        "data_dir": str(settings.data_dir),
        "inbox_dir": str(settings.inbox_dir),
    }
    updated = data(client.put("/api/settings", json={"buyer_name": "某某大学", "overdue_days": 15}))
    assert updated["buyer_name"] == "某某大学"
    assert updated["overdue_days"] == 15
    assert client.put("/api/settings", json={"overdue_days": 0}).status_code == 422


def test_categories_crud(client):
    categories = data(client.get("/api/categories"))
    assert len(categories) == 11
    assert set(categories[0]) == {
        "id",
        "name",
        "color",
        "keywords",
        "route_hint",
        "sort",
        "archived",
    }

    created = data(client.post("/api/categories", json={"name": "培训", "keywords": ["培训费"]}))
    assert created["sort"] == 11
    assert created["color"] == "gray"
    assert client.post("/api/categories", json={"name": "培训"}).status_code == 409
    assert client.post("/api/categories", json={"name": "  "}).status_code == 422

    patched = data(client.patch(f"/api/categories/{created['id']}", json={"color": "pink"}))
    assert patched["color"] == "pink"
    assert (
        client.patch(f"/api/categories/{created['id']}", json={"name": "办公用品"}).status_code
        == 409
    )

    assert data(client.delete(f"/api/categories/{created['id']}")) is None
    archived = next(c for c in data(client.get("/api/categories")) if c["id"] == created["id"])
    assert archived["archived"] is True
    assert client.delete("/api/categories/999").status_code == 404


def test_projects_crud(client):
    assert data(client.get("/api/projects")) == []
    project = data(client.post("/api/projects", json={"name": "科研A", "code": "KY001"}))
    assert project == {
        "id": project["id"],
        "code": "KY001",
        "name": "科研A",
        "owner": "",
        "active": True,
    }
    patched = data(client.patch(f"/api/projects/{project['id']}", json={"owner": "张三"}))
    assert patched["owner"] == "张三"
    assert data(client.delete(f"/api/projects/{project['id']}")) is None
    assert data(client.get("/api/projects"))[0]["active"] is False
    assert client.patch("/api/projects/999", json={"owner": "x"}).status_code == 404
    assert client.post("/api/projects", json={"code": "x"}).status_code == 422


def test_checklist_rules_crud(client):
    rules = data(client.get("/api/checklist-rules"))
    assert rules and set(rules[0]) == {
        "id",
        "category_id",
        "attachment_kind",
        "level",
        "condition",
        "hint",
    }

    created = data(
        client.post(
            "/api/checklist-rules",
            json={
                "category_id": None,
                "attachment_kind": "statement",
                "level": "suggested",
                "condition": {"amount_gte": 500000, "is_online": True},
                "hint": "大额网购附说明",
            },
        )
    )
    assert created["condition"] == {"amount_gte": 500000, "is_online": True}

    patched = data(
        client.patch(f"/api/checklist-rules/{created['id']}", json={"level": "required"})
    )
    assert patched["level"] == "required"
    assert data(client.delete(f"/api/checklist-rules/{created['id']}")) is None
    assert client.delete(f"/api/checklist-rules/{created['id']}").status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"attachment_kind": "nope", "level": "required", "condition": {}, "hint": ""},
        {"attachment_kind": "order", "level": "must", "condition": {}, "hint": ""},
        {
            "attachment_kind": "order",
            "level": "required",
            "condition": {"online": True},
            "hint": "",
        },
        {
            "attachment_kind": "order",
            "level": "required",
            "condition": {"amount_gte": "1"},
            "hint": "",
        },
    ],
)
def test_checklist_rule_validation(client, payload):
    response = client.post("/api/checklist-rules", json={"category_id": None, **payload})
    assert response.status_code == 422


def test_checklist_rule_unknown_category(client):
    response = client.post(
        "/api/checklist-rules",
        json={
            "category_id": 999,
            "attachment_kind": "order",
            "level": "required",
            "condition": {},
            "hint": "",
        },
    )
    assert response.status_code == 404


def test_backup_endpoint_creates_file(client, settings):
    result = data(client.post("/api/backup"))
    path = Path(result["file"])
    assert path.is_file()
    assert path.parent == settings.backup_dir
