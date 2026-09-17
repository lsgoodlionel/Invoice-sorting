"""联调阶段发现的跨模块问题回归测试。"""

import io

from PIL import Image

from invoice_sorting.attachments.storage import guess_kind
from invoice_sorting.common.constants import AttachmentKind


def png_bytes(color: str = "red") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), color).save(buffer, format="PNG")
    return buffer.getvalue()


def create(client, **overrides) -> dict:
    payload = {"spent_on": "2026-09-15", "amount_cents": 96000, "merchant": "京东"}
    payload.update(overrides)
    response = client.post("/api/expenses", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def upload(client, expense_id: int, name: str, content: bytes, kind: str = "invoice"):
    return client.post(
        f"/api/expenses/{expense_id}/attachments",
        files=[("files", (name, content, "application/octet-stream"))],
        data={"kind": kind},
    )


def make_batch(client, name: str = "第1批") -> dict:
    return client.post("/api/batches", json={"name": name}).json()["data"]


def test_list_missing_filter_returns_only_expenses_with_required_gaps(client):
    missing = create(client)
    complete = create(client, amount_cents=1000, merchant="便利店")
    upload(client, complete["id"], "fp.png", png_bytes("blue"))

    data = client.get("/api/expenses?missing=true").json()["data"]

    ids = [row["id"] for row in data["items"]]
    assert ids == [missing["id"]]
    assert data["total"] == 1


def test_deleted_expense_files_can_be_imported_again(client):
    content = png_bytes("green")
    first = create(client)
    assert upload(client, first["id"], "发票.png", content).status_code == 200
    client.delete(f"/api/expenses/{first['id']}")

    second = create(client)
    response = upload(client, second["id"], "发票.png", content)

    assert response.status_code == 200, response.text


def test_delete_expense_removes_it_from_draft_batch(client):
    expense = create(client, amount_cents=1000)
    upload(client, expense["id"], "fp.png", png_bytes())
    batch = make_batch(client)
    client.post(f"/api/batches/{batch['id']}/items", json={"add": [expense["id"]], "force": True})

    client.delete(f"/api/expenses/{expense['id']}")

    detail = client.get(f"/api/batches/{batch['id']}").json()["data"]
    assert detail["item_count"] == 0


def test_voiding_expense_removes_it_from_draft_batch(client):
    expense = create(client, amount_cents=1000)
    upload(client, expense["id"], "fp.png", png_bytes())
    batch = make_batch(client)
    client.post(f"/api/batches/{batch['id']}/items", json={"add": [expense["id"]], "force": True})

    response = client.post(
        f"/api/expenses/{expense['id']}/status", json={"status": "void", "note": "个人承担"}
    )

    assert response.json()["data"]["batch_id"] is None
    assert response.json()["data"]["status"] == "void"


def test_cannot_void_or_delete_expense_in_sent_batch(client):
    expense = create(client, amount_cents=1000)
    upload(client, expense["id"], "fp.png", png_bytes())
    batch = make_batch(client)
    client.post(f"/api/batches/{batch['id']}/items", json={"add": [expense["id"]], "force": True})
    client.post(f"/api/batches/{batch['id']}/sent", json={"sent_on": "2026-09-20"})

    void = client.post(
        f"/api/expenses/{expense['id']}/status", json={"status": "void", "note": "x"}
    )
    delete = client.delete(f"/api/expenses/{expense['id']}")

    assert void.status_code == 409
    assert delete.status_code == 409
    assert "重新打开" in delete.json()["error"]


def test_guess_kind_does_not_treat_fp_substring_as_invoice():
    assert guess_kind("dfpx_screenshot.png") == AttachmentKind.OTHER
    assert guess_kind("电子发票.pdf") == AttachmentKind.INVOICE
