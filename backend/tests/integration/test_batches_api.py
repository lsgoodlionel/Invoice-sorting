"""批次 API：CRUD、加入/移出校验（409）、外发、到账、撤销（T12/T13）。"""

from tests.integration.test_batches_helpers import (
    add_items,
    batch_with,
    category_id,
    expense_detail,
    make_batch,
    make_expense,
    project_id,
)

BATCH_KEYS = {
    "id", "name", "project_id", "project_name", "status", "status_label", "sent_on", "sent_via",
    "receiver", "external_no", "received_on", "received_cents", "note", "created_at",
    "created_by", "item_count", "total_cents", "missing_item_count",
}  # fmt: skip


def test_create_list_get_patch_batch(client):
    project = project_id(client, "科研A")
    created = make_batch(client, "第1批", project_id=project, note="备注")
    assert set(created) == BATCH_KEYS | {"expenses", "exports"}
    assert created["status"] == "draft"
    assert created["status_label"] == "待外发"
    assert created["project_name"] == "科研A"
    assert created["created_at"].endswith("+08:00")

    listed = client.get("/api/batches").json()["data"]
    assert [set(row) for row in listed] == [BATCH_KEYS]
    assert client.get("/api/batches?status=sent").json()["data"] == []
    assert client.get("/api/batches?status=bad").status_code == 422

    patched = client.patch(
        f"/api/batches/{created['id']}",
        json={"name": "改名", "project_id": None, "receiver": "王老师", "note": None},
    ).json()["data"]
    assert patched["name"] == "改名"
    assert patched["project_id"] is None
    assert patched["receiver"] == "王老师"
    assert patched["note"] == ""
    assert client.get(f"/api/batches/{created['id']}").json()["data"]["name"] == "改名"


def test_batch_validation_and_not_found(client):
    assert client.post("/api/batches", json={"name": ""}).status_code == 422
    missing_project = client.post("/api/batches", json={"name": "x", "project_id": 999})
    assert missing_project.status_code == 404
    assert missing_project.json()["error"] == "经费项目不存在"
    assert client.get("/api/batches/999").json()["error"] == "批次不存在"
    batch = make_batch(client)
    assert client.patch(f"/api/batches/{batch['id']}", json={"name": None}).status_code == 422


def test_items_counts_and_remove(client):
    batch, expenses = batch_with(client, 3)
    assert batch["item_count"] == 3
    assert batch["total_cents"] == sum(e["amount_cents"] for e in expenses)
    assert batch["missing_item_count"] == 0
    assert [e["id"] for e in batch["expenses"]] == [e["id"] for e in expenses]
    assert batch["expenses"][0]["batch_name"] == "第1批"

    first = expenses[0]["id"]
    response = client.post(f"/api/batches/{batch['id']}/items", json={"remove": [first]})
    detail = response.json()["data"]
    assert detail["item_count"] == 2
    assert expense_detail(client, first)["batch_id"] is None

    client.delete(f"/api/expenses/{expenses[1]['id']}")
    assert client.get(f"/api/batches/{batch['id']}").json()["data"]["item_count"] == 1


def test_items_noop_and_remove_errors(client):
    batch, expenses = batch_with(client, 1)
    same = client.post(f"/api/batches/{batch['id']}/items", json={}).json()["data"]
    assert same["item_count"] == 1
    again = add_items(client, batch["id"], [expenses[0]["id"]])
    assert again.json()["data"]["item_count"] == 1  # 已在本批次，忽略
    outsider = make_expense(client, merchant="外人")
    response = client.post(f"/api/batches/{batch['id']}/items", json={"remove": [outsider["id"]]})
    assert response.status_code == 400
    assert "不在该批次中" in response.json()["error"]
    assert add_items(client, batch["id"], [9999]).status_code == 404


def test_add_rejects_other_batch_and_void(client):
    first, expenses = batch_with(client, 1, name="甲批")
    second = make_batch(client, "乙批")
    response = add_items(client, second["id"], [expenses[0]["id"]], force=True)
    assert response.status_code == 409
    assert "已在批次『甲批』中" in response.json()["error"]

    void = make_expense(client, merchant="退货")
    client.post(f"/api/expenses/{void['id']}/status", json={"status": "void", "note": "退货"})
    response = add_items(client, second["id"], [void["id"]], force=True)
    assert response.status_code == 409
    assert "已作废" in response.json()["error"]


def test_add_with_missing_items_requires_force(client):
    batch = make_batch(client)
    complete = make_expense(client, merchant="齐全")
    lacking = make_expense(
        client, merchant="京东", cents=96000, category_id=category_id(client, "易耗品")
    )
    response = add_items(client, batch["id"], [complete["id"], lacking["id"]])
    assert response.status_code == 409
    error = response.json()["error"]
    assert error == (
        f"以下记录仍缺少必需凭证：#{lacking['id']} 京东 960.00（缺 2 项）；如仍要加入请确认"
    )
    assert client.get(f"/api/batches/{batch['id']}").json()["data"]["item_count"] == 0

    forced = add_items(client, batch["id"], [complete["id"], lacking["id"]], force=True)
    assert forced.status_code == 200
    assert forced.json()["data"]["missing_item_count"] == 1


def test_project_mismatch_and_auto_project(client):
    project_a, project_b = project_id(client, "科研A"), project_id(client, "科研B")
    auto = make_batch(client, "自动")
    in_a = [make_expense(client, merchant=f"A{i}", project_id=project_a) for i in range(2)]
    detail = add_items(client, auto["id"], [e["id"] for e in in_a]).json()["data"]
    assert detail["project_id"] == project_a  # 首次加入且项目相同 → 自动设置

    in_b = make_expense(client, merchant="B店", project_id=project_b)
    no_project = make_expense(client, merchant="散户")
    response = add_items(client, auto["id"], [in_b["id"], no_project["id"]])
    assert response.status_code == 409
    error = response.json()["error"]
    assert error.startswith("项目不一致：批次项目为『科研A』")
    assert "B店" in error and "属于『科研B』" in error and "属于无项目" in error
    forced = add_items(client, auto["id"], [in_b["id"], no_project["id"]], force=True)
    assert forced.json()["data"]["item_count"] == 4

    mixed = make_batch(client, "混合")
    others = [make_expense(client, merchant="C", project_id=project_a), make_expense(client)]
    detail = add_items(client, mixed["id"], [e["id"] for e in others]).json()["data"]
    assert detail["project_id"] is None


def test_sent_marks_all_expenses_sent(client):
    batch, expenses = batch_with(client, 3)
    manual = expenses[0]["id"]
    client.post(f"/api/expenses/{manual}/status", json={"status": "invoiced"})
    response = client.post(
        f"/api/batches/{batch['id']}/sent",
        json={
            "sent_on": "2026-10-08",
            "sent_via": "邮件",
            "receiver": "王老师",
            "external_no": "Y1",
        },
    )
    assert response.status_code == 200, response.text
    detail = response.json()["data"]
    assert detail["status"] == "sent"
    assert (detail["sent_on"], detail["sent_via"], detail["external_no"]) == (
        "2026-10-08",
        "邮件",
        "Y1",
    )
    for expense in expenses:  # T12
        item = expense_detail(client, expense["id"])
        assert item["status"] == "sent"
        assert item["sent_on"] == "2026-10-08"
        assert item["status_manual"] is False
        assert item["timeline"][-1]["note"] == "批次『第1批』已外发"

    blocked = add_items(client, batch["id"], [make_expense(client)["id"]])
    assert blocked.status_code == 409
    assert blocked.json()["error"] == "批次已外发，不能修改"
    assert (
        client.post(f"/api/batches/{batch['id']}/sent", json={"sent_on": "2026-10-09"}).status_code
        == 409
    )
    assert client.delete(f"/api/batches/{batch['id']}").status_code == 409


def test_sent_rejects_empty_batch(client):
    batch = make_batch(client)
    response = client.post(f"/api/batches/{batch['id']}/sent", json={"sent_on": "2026-10-08"})
    assert response.status_code == 400
    assert response.json()["error"] == "空批次不能外发"


def test_partial_then_full_received(client):
    batch, expenses = batch_with(client, 8)
    ids = [e["id"] for e in expenses]
    not_sent = client.post(
        f"/api/batches/{batch['id']}/received", json={"received_on": "2026-11-01"}
    )
    assert not_sent.status_code == 409
    client.post(f"/api/batches/{batch['id']}/sent", json={"sent_on": "2026-10-08"})

    outsider = make_expense(client, merchant="外人")
    bad = client.post(
        f"/api/batches/{batch['id']}/received",
        json={"received_on": "2026-11-01", "expense_ids": [outsider["id"]]},
    )
    assert bad.status_code == 400

    partial = client.post(
        f"/api/batches/{batch['id']}/received",
        json={"received_on": "2026-11-10", "expense_ids": ids[:6]},
    ).json()["data"]
    assert partial["status"] == "partial"  # T13
    assert partial["received_on"] == "2026-11-10"
    assert partial["received_cents"] == sum(e["amount_cents"] for e in expenses[:6])
    statuses = [expense_detail(client, i)["status"] for i in ids]
    assert statuses == ["reimbursed"] * 6 + ["sent"] * 2
    reimbursed = expense_detail(client, ids[0])
    assert (reimbursed["reimbursed_on"], reimbursed["reimbursed_cents"]) == (
        "2026-11-10",
        expenses[0]["amount_cents"],
    )

    full = client.post(
        f"/api/batches/{batch['id']}/received", json={"received_on": "2026-11-20"}
    ).json()["data"]
    assert full["status"] == "received"
    assert full["received_on"] == "2026-11-20"
    assert full["received_cents"] == full["total_cents"]
    again = client.post(f"/api/batches/{batch['id']}/received", json={"received_on": "2026-11-21"})
    assert again.status_code == 409


def test_reopen_resets_batch_and_expenses(client):
    batch, expenses = batch_with(client, 2)
    assert client.post(f"/api/batches/{batch['id']}/reopen").status_code == 409
    client.post(f"/api/batches/{batch['id']}/sent", json={"sent_on": "2026-10-08"})
    client.post(f"/api/batches/{batch['id']}/received", json={"received_on": "2026-11-08"})
    detail = client.post(f"/api/batches/{batch['id']}/reopen").json()["data"]
    assert detail["status"] == "draft"
    assert (detail["sent_on"], detail["received_on"], detail["received_cents"]) == (None, None, 0)
    for expense in expenses:
        item = expense_detail(client, expense["id"])
        assert item["status"] == "complete"
        assert (item["sent_on"], item["reimbursed_on"], item["reimbursed_cents"]) == (None, None, 0)


def test_delete_draft_batch_releases_expenses(client):
    batch, expenses = batch_with(client, 2)
    client.delete(f"/api/expenses/{expenses[1]['id']}")
    assert client.delete(f"/api/batches/{batch['id']}").json() == {
        "ok": True,
        "data": None,
        "error": None,
    }
    assert client.get(f"/api/batches/{batch['id']}").status_code == 404
    item = expense_detail(client, expenses[0]["id"])
    assert (item["batch_id"], item["status"]) == (None, "complete")
