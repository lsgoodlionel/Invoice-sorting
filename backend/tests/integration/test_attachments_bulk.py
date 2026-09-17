"""待归属附件批量删除、批量归属/移回/改类型。"""

import pytest
from sqlalchemy import select

from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.db.models import Attachment, Category, MerchantMemory
from invoice_sorting.settings.service import update_app_settings
from tests.invoice_factory import store_invoice

INVOICE = {"invoice_no": "26312000000000000011", "seller_name": "上海文具店", "total_cents": 960}


def body(response, status: int = 200):
    assert response.status_code == status, response.text
    return response.json()


def create_expense(client, **overrides) -> dict:
    payload = {"spent_on": "2026-09-15", "amount_cents": 960, "merchant": "文具店", **overrides}
    return body(client.post("/api/expenses", json=payload))["data"]


@pytest.fixture
def pending(app, settings, tmp_path):
    """入库三个待归属附件：发票、订单截图、无发票数据的 PDF。"""
    with app.state.session_factory() as session:
        invoice = store_invoice(session, settings, tmp_path, invoice=dict(INVOICE))
        order = store_invoice(
            session, settings, tmp_path, name="订单.pdf", kind=AttachmentKind.ORDER
        )
        other = store_invoice(
            session, settings, tmp_path, name="其他.pdf", kind=AttachmentKind.OTHER
        )
        session.commit()
        return {"invoice": invoice.id, "order": order.id, "other": other.id}


def unassigned_ids(client) -> set[int]:
    return {item["id"] for item in body(client.get("/api/attachments/unassigned"))["data"]}


def test_bulk_delete_moves_files_to_trash(client, settings, pending):
    ids = [pending["invoice"], pending["order"]]

    result = body(client.post("/api/attachments/bulk-delete", json={"ids": ids + ids[:1]}))

    assert result["data"] == {"deleted": 2}
    assert unassigned_ids(client) == {pending["other"]}
    trashed = sorted(path.name for path in settings.trash_dir.iterdir())
    assert len(trashed) == 2 and all(name.startswith("A0000") for name in trashed)


def test_bulk_delete_rejects_assigned_attachments(client, pending):
    expense = create_expense(client)
    body(client.patch(f"/api/attachments/{pending['order']}", json={"expense_id": expense["id"]}))

    response = client.post(
        "/api/attachments/bulk-delete", json={"ids": [pending["invoice"], pending["order"]]}
    )

    error = body(response, 409)["error"]
    assert "已归属" in error and f"#{pending['order']}" in error
    assert pending["invoice"] in unassigned_ids(client)


@pytest.mark.parametrize(
    ("payload", "status"),
    [({"ids": []}, 422), ({"ids": [0]}, 422), ({"ids": [99999]}, 404), ({}, 422)],
)
def test_bulk_delete_validates_ids(client, payload, status):
    response = client.post("/api/attachments/bulk-delete", json=payload)
    assert response.status_code == status
    if status == 404:
        assert "#99999" in response.json()["error"]


def test_bulk_assign_to_expense_confirms_invoice_and_updates_status(client, session, pending):
    office = session.scalar(select(Category.id).where(Category.name == "其他"))
    expense = create_expense(client, category_id=office)
    ids = [pending["invoice"], pending["order"]]

    items = body(
        client.post("/api/attachments/bulk-assign", json={"ids": ids, "expense_id": expense["id"]})
    )["data"]

    assert [item["id"] for item in items] == ids
    assert all(item["expense_id"] == expense["id"] for item in items)
    assert items[0]["invoice"]["confirmed"] is True
    detail = body(client.get(f"/api/expenses/{expense['id']}"))["data"]
    assert detail["status"] == "complete" and detail["attachment_count"] == 2
    # 批量归属不是用户对分类的明确修改，不写入分类记忆
    assert session.get(MerchantMemory, "上海文具店") is None
    assert unassigned_ids(client) == {pending["other"]}


def test_bulk_assign_can_change_kind_and_move_back(client, pending):
    expense = create_expense(client)
    ids = [pending["other"]]

    items = body(
        client.post(
            "/api/attachments/bulk-assign",
            json={"ids": ids, "expense_id": expense["id"], "kind": "payment"},
        )
    )["data"]
    assert items[0]["kind"] == "payment" and items[0]["expense_id"] == expense["id"]

    moved = body(
        client.post(
            "/api/attachments/bulk-assign",
            json={"ids": ids + [pending["invoice"]], "expense_id": None},
        )
    )["data"]
    assert all(item["expense_id"] is None for item in moved)
    assert moved[1]["invoice"]["confirmed"] is False
    assert body(client.get(f"/api/expenses/{expense['id']}"))["data"]["attachment_count"] == 0


def test_bulk_assign_kind_only_keeps_unassigned(client, pending):
    items = body(
        client.post(
            "/api/attachments/bulk-assign",
            json={"ids": [pending["other"]], "expense_id": None, "kind": "order"},
        )
    )["data"]
    assert items[0]["kind"] == "order" and items[0]["expense_id"] is None


def test_bulk_assign_moves_between_expenses_and_refreshes_both(client, pending):
    first = create_expense(client)
    second = create_expense(client, merchant="另一家")
    ids = [pending["invoice"]]
    client.post("/api/attachments/bulk-assign", json={"ids": ids, "expense_id": first["id"]})
    assert body(client.get(f"/api/expenses/{first['id']}"))["data"]["status"] != "spent"

    client.post("/api/attachments/bulk-assign", json={"ids": ids, "expense_id": second["id"]})

    assert body(client.get(f"/api/expenses/{first['id']}"))["data"]["status"] == "spent"
    assert body(client.get(f"/api/expenses/{second['id']}"))["data"]["status"] != "spent"


def test_bulk_assign_rejects_missing_or_deleted_expense(client, pending):
    expense = create_expense(client)
    client.delete(f"/api/expenses/{expense['id']}")
    for expense_id in (expense["id"], 99999):
        response = client.post(
            "/api/attachments/bulk-assign",
            json={"ids": [pending["order"]], "expense_id": expense_id},
        )
        assert response.status_code == 404
    assert client.post("/api/attachments/bulk-assign", json={"ids": [1]}).status_code == 422
    assert pending["order"] in unassigned_ids(client)


def test_serialized_invoice_reflects_region_settings(client, app, settings, tmp_path):
    with app.state.session_factory() as session:
        attachment = store_invoice(
            session,
            settings,
            tmp_path,
            invoice={"region_name": "北京", "seller_name": "北京京东世纪贸易有限公司"},
        )
        update_app_settings(session, detail_platforms=["当当"])
        session.commit()
        attachment_id = attachment.id
    item = next(
        i
        for i in body(client.get("/api/attachments/unassigned"))["data"]
        if i["id"] == attachment_id
    )
    assert item["invoice"]["is_nonlocal"] is True and item["invoice"]["detail_platform"] is False
    with app.state.session_factory() as session:
        assert session.get(Attachment, attachment_id).invoice_data.region_name == "北京"
