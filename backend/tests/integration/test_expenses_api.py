"""支出记录 API（T04–T08、T15、T18）。"""

import io
from datetime import date

import pytest
from PIL import Image

from invoice_sorting.db.models import Batch


def png_bytes(color: str = "red") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (12, 12), color).save(buffer, format="PNG")
    return buffer.getvalue()


def category_id(client, name: str) -> int:
    categories = client.get("/api/categories").json()["data"]
    return next(item["id"] for item in categories if item["name"] == name)


def create(client, **overrides) -> dict:
    payload = {"spent_on": "2026-09-15", "amount_cents": 96000, "merchant": "京东××店"}
    payload.update(overrides)
    response = client.post("/api/expenses", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def upload(client, expense_id: int, files: list[tuple[str, bytes]], kind: str | None = None):
    multipart = [("files", (name, content, "application/octet-stream")) for name, content in files]
    data = {"kind": kind} if kind else {}
    return client.post(f"/api/expenses/{expense_id}/attachments", files=multipart, data=data)


def item(detail: dict, kind: str) -> dict:
    return next(entry for entry in detail["checklist"] if entry["attachment_kind"] == kind)


DETAIL_KEYS = {
    "id", "spent_on", "amount_cents", "merchant", "summary", "category_id", "category_name",
    "category_color", "project_id", "project_name", "status", "status_label", "status_manual",
    "missing_count", "batch_id", "batch_name", "attachment_count", "invoice_no", "pay_method",
    "is_online", "note", "void_reason", "sent_on", "reimbursed_on", "reimbursed_cents",
    "folder_path", "route_hint", "attachments", "checklist", "timeline", "created_at",
    "updated_at", "region_name", "is_nonlocal",
}  # fmt: skip


def test_create_returns_detail_shape(client):
    detail = create(client, category_id=category_id(client, "易耗品"), summary="鼠标×2")
    assert set(detail) == DETAIL_KEYS
    assert detail["region_name"] == "" and detail["is_nonlocal"] is False
    assert detail["status"] == "spent"
    assert detail["status_label"] == "已支出"
    assert detail["category_name"] == "易耗品"
    assert "设备与实验室" in detail["route_hint"]
    assert detail["missing_count"] == 3
    assert detail["timeline"][0]["to_status"] == "spent"
    assert detail["created_at"].endswith("+08:00")


@pytest.mark.parametrize(
    "payload",
    [
        {"spent_on": "2026-09-15", "amount_cents": 1},
        {"spent_on": "2026-09-15", "amount_cents": -1, "merchant": "x"},
        {"spent_on": "bad", "amount_cents": 1, "merchant": "x"},
        {"spent_on": "2026-09-15", "amount_cents": 1.5, "merchant": "x"},
    ],
)
def test_create_validates_payload(client, payload):
    response = client.post("/api/expenses", json=payload)
    assert response.status_code == 422
    assert response.json()["ok"] is False


def test_create_with_unknown_category_is_404(client):
    response = client.post(
        "/api/expenses",
        json={"spent_on": "2026-09-15", "amount_cents": 1, "merchant": "x", "category_id": 999},
    )
    assert response.status_code == 404
    assert response.json()["error"] == "分类不存在"


def test_get_unknown_expense_is_404(client):
    response = client.get("/api/expenses/12345")
    assert response.status_code == 404
    assert response.json() == {"ok": False, "data": None, "error": "支出记录不存在"}


def test_upload_guesses_kind_and_rejects_duplicates_and_bad_types(client):
    expense = create(client, category_id=category_id(client, "易耗品"))
    response = upload(
        client, expense["id"], [("订单截图.png", png_bytes()), ("x.png", png_bytes("blue"))]
    )
    assert response.status_code == 200, response.text
    detail = response.json()["data"]
    kinds = sorted(a["kind"] for a in detail["attachments"])
    assert kinds == ["order", "other"]
    assert item(detail, "order")["state"] == "present"
    assert detail["attachment_count"] == 2

    duplicate = upload(client, expense["id"], [("again.png", png_bytes())])
    assert duplicate.status_code == 409
    assert "文件已存在" in duplicate.json()["error"]

    bad = upload(client, expense["id"], [("evil.pdf", b"MZ\x90\x00binary")])
    assert bad.status_code == 400
    assert "不支持" in bad.json()["error"]


def test_upload_with_explicit_kind_and_invalid_kind(client):
    expense = create(client)
    ok = upload(client, expense["id"], [("a.png", png_bytes())], kind="payment")
    assert ok.json()["data"]["attachments"][0]["kind"] == "payment"
    bad = upload(client, expense["id"], [("b.png", png_bytes("green"))], kind="nope")
    assert bad.status_code == 422


def test_evidence_complete_flow_and_manual_status_sticks(client):
    expense = create(client, category_id=category_id(client, "易耗品"))
    upload(client, expense["id"], [("发票.png", png_bytes("red"))])
    detail = upload(client, expense["id"], [("订单.png", png_bytes("green"))]).json()["data"]
    assert detail["status"] == "invoiced"

    patched = client.patch(
        f"/api/checklist-items/{item(detail, 'acceptance')['id']}",
        json={"state": "not_needed", "reason": "平台未要求"},
    )
    detail = patched.json()["data"]
    assert detail["status"] == "complete"  # T06
    assert item(detail, "acceptance")["reason"] == "平台未要求"

    manual = client.post(f"/api/expenses/{expense['id']}/status", json={"status": "complete"})
    assert manual.json()["data"]["status_manual"] is True
    order = next(a for a in detail["attachments"] if a["kind"] == "order")
    assert client.delete(f"/api/attachments/{order['id']}").json() == {
        "ok": True, "data": None, "error": None,
    }  # fmt: skip
    detail = client.get(f"/api/expenses/{expense['id']}").json()["data"]
    assert detail["status"] == "complete"  # T07
    assert detail["missing_count"] == 1


def test_checklist_item_patch_validation(client):
    expense = create(client)
    invoice_item = item(expense, "invoice")
    assert (
        client.patch(
            f"/api/checklist-items/{invoice_item['id']}", json={"state": "present"}
        ).status_code
        == 422
    )
    assert client.patch("/api/checklist-items/9999", json={"state": "missing"}).status_code == 404
    restored = client.patch(
        f"/api/checklist-items/{invoice_item['id']}", json={"state": "not_needed"}
    )
    assert item(restored.json()["data"], "invoice")["state"] == "not_needed"
    restored = client.patch(f"/api/checklist-items/{invoice_item['id']}", json={"state": "missing"})
    assert item(restored.json()["data"], "invoice")["state"] == "missing"


def test_patch_category_and_online_recomputes_checklist(client):
    expense = create(client, category_id=category_id(client, "易耗品"))
    client.patch(
        f"/api/checklist-items/{item(expense, 'order')['id']}", json={"state": "not_needed"}
    )
    response = client.patch(
        f"/api/expenses/{expense['id']}",
        json={"category_id": category_id(client, "办公用品"), "is_online": True},
    )
    detail = response.json()["data"]
    assert item(detail, "order")["state"] == "not_needed"  # T08
    assert all(entry["attachment_kind"] != "acceptance" for entry in detail["checklist"])


def test_patch_renames_folder_and_attachment_still_opens(client):
    expense = create(client)
    detail = upload(client, expense["id"], [("支付.png", png_bytes())]).json()["data"]
    old_folder = detail["folder_path"]

    patched = client.patch(
        f"/api/expenses/{expense['id']}", json={"amount_cents": 12345, "merchant": "新商家"}
    ).json()["data"]

    assert patched["folder_path"] != old_folder
    assert "新商家" in patched["folder_path"] and "123.45" in patched["folder_path"]
    file_response = client.get(patched["attachments"][0]["url"])
    assert file_response.status_code == 200
    assert file_response.content == png_bytes()  # T18


def test_patch_can_clear_nullable_fields_and_rejects_null_required(client):
    expense = create(client, category_id=category_id(client, "易耗品"))
    cleared = client.patch(f"/api/expenses/{expense['id']}", json={"category_id": None})
    assert cleared.json()["data"]["category_id"] is None
    bad = client.patch(f"/api/expenses/{expense['id']}", json={"amount_cents": None})
    assert bad.status_code == 422


def test_status_endpoint_void_requires_note_and_can_restore(client):
    expense = create(client)
    url = f"/api/expenses/{expense['id']}/status"
    missing_note = client.post(url, json={"status": "void"})
    assert missing_note.status_code == 400
    assert "原因" in missing_note.json()["error"]

    voided = client.post(url, json={"status": "void", "note": "个人承担"}).json()["data"]
    assert voided["status"] == "void"
    assert voided["void_reason"] == "个人承担"
    assert voided["timeline"][-1]["is_manual"] is True

    restored = client.post(url, json={"status": None}).json()["data"]
    assert restored["status"] == "spent"
    assert restored["status_manual"] is False
    assert client.post(url, json={"status": "bogus"}).status_code == 422


def test_delete_soft_deletes(client):
    expense = create(client)
    upload(client, expense["id"], [("a.png", png_bytes())])
    assert client.delete(f"/api/expenses/{expense['id']}").json()["data"] is None
    assert client.get(f"/api/expenses/{expense['id']}").status_code == 404
    assert client.get("/api/expenses").json()["data"]["total"] == 0


@pytest.fixture
def listing(client, app):
    cat = category_id(client, "易耗品")
    a = create(client, spent_on="2026-07-01", amount_cents=100, merchant="京东", category_id=cat)
    b = create(
        client, spent_on="2026-09-10", amount_cents=200, merchant="腾讯云", summary="会议会员"
    )
    c = create(client, spent_on="2026-09-20", amount_cents=400, merchant="滴滴出行")
    client.post(f"/api/expenses/{c['id']}/status", json={"status": "void", "note": "个人出行"})
    factory = app.state.session_factory
    with factory() as session:
        batch = Batch(name="2026-09 第1批", status="sent", sent_on=date(2026, 10, 8))
        session.add(batch)
        session.flush()
        from invoice_sorting.db.models import Expense

        row = session.get(Expense, b["id"])
        row.batch_id, row.sent_on = batch.id, date(2026, 10, 8)
        session.commit()
        batch_id = batch.id
    client.post(f"/api/expenses/{b['id']}/status", json={"status": None})
    return {"a": a["id"], "b": b["id"], "c": c["id"], "cat": cat, "batch": batch_id}


def list_ids(client, query: str = "") -> list[int]:
    response = client.get(f"/api/expenses{query}")
    assert response.status_code == 200, response.text
    return [row["id"] for row in response.json()["data"]["items"]]


def test_list_summary_totals_and_status_counts(client, listing):
    data = client.get("/api/expenses").json()["data"]
    assert data["total"] == 3
    assert data["total_cents"] == 700
    assert data["status_counts"]["void"] == {"count": 1, "amount_cents": 400}
    assert data["status_counts"]["sent"] == {"count": 1, "amount_cents": 200}
    row = next(r for r in data["items"] if r["id"] == listing["b"])
    assert row["batch_name"] == "2026-09 第1批"
    assert row["status"] == "sent"
    assert "folder_path" not in row


def test_list_filters(client, listing):
    assert list_ids(client, "?status=spent,void") == [listing["c"], listing["a"]]
    assert list_ids(client, "?start=2026-09-01&end=2026-09-30") == [listing["c"], listing["b"]]
    assert list_ids(client, "?start=2026-10-01&end=2026-10-31&date_basis=sent") == [listing["b"]]
    assert list_ids(client, "?q=会员") == [listing["b"]]
    assert list_ids(client, f"?category_id={listing['cat']}") == [listing["a"]]
    assert list_ids(client, f"?batch_id={listing['batch']}") == [listing["b"]]
    assert list_ids(client, "?unbatched=true") == [listing["c"], listing["a"]]


def test_list_status_counts_ignore_status_filter(client, listing):
    data = client.get("/api/expenses?status=void").json()["data"]
    assert data["total"] == 1
    assert data["status_counts"]["spent"]["count"] == 1


def test_list_pagination(client, listing):
    assert list_ids(client, "?page=2&page_size=1") == [listing["b"]]
    assert client.get("/api/expenses?page_size=501").status_code == 422
    assert client.get("/api/expenses?page=0").status_code == 422
    assert client.get("/api/expenses?status=unknown").status_code == 422
