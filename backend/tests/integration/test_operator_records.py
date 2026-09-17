"""操作人记录：不同用户补全同一套凭证、状态事件操作人、批次与导出、收件箱为空、线程池上下文。"""

import shutil
import threading
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from invoice_sorting.auth.context import acting_as, current_user_id
from invoice_sorting.db.models import Attachment
from invoice_sorting.importer.watcher import process_inbox_once
from tests.auth_helpers import create_user, logged_in_client
from tests.conftest import FIXTURES_DIR
from tests.evidence_factory import png, recognized
from tests.integration.test_import_groups_api import (
    JD_ORDER_NO,
    chatgpt_bank,
    confirm,
    detail,
    jd_invoice,
    payload,
    upload,
)


def chatgpt_order():
    fields = {"amount_cents": 2000, "currency": "USD", "occurred_on": date(2026, 3, 5)}
    return recognized(
        "order", merchant="OpenAI", item_name="ChatGPT Plus", is_foreign=True, **fields
    )


def ref(user: dict) -> dict:
    return {"id": user["id"], "display_name": user["display_name"]}


def test_two_users_complete_one_expense(auth_app, admin_client, tmp_path, fake_recognition):
    alice = create_user(admin_client, "alice", display_name="爱丽丝")
    bob = create_user(admin_client, "bob", display_name="鲍勃")
    alice_client = logged_in_client(auth_app, "alice")
    bob_client = logged_in_client(auth_app, "bob")

    first = upload(alice_client, jd_invoice(tmp_path))
    expense_id = confirm(alice_client, first, payload(first["groups"][0]))["created"][0]
    order_png = png(tmp_path / "uploads", "订单截图.png")
    fake_recognition.set(order_png.name, recognized("order", order_no=JD_ORDER_NO))
    second = upload(bob_client, order_png)
    assert second["groups"][0]["attachments"][0]["uploaded_by"] == ref(bob)
    confirm(bob_client, second, payload(second["groups"][0], "attach", expense_id=expense_id))

    expense = detail(admin_client, expense_id)
    uploaders = {a["kind"]: a["uploaded_by"] for a in expense["attachments"]}
    assert uploaders == {"invoice": ref(alice), "order": ref(bob)}
    assert expense["created_by"] == ref(alice)
    assert [event["actor"] for event in expense["timeline"]] == [ref(alice), ref(alice)]
    listed = admin_client.get("/api/expenses").json()["data"]["items"][0]
    assert listed["created_by"] == ref(alice)


def test_auto_status_change_records_triggering_user(
    auth_app, admin_client, tmp_path, fake_recognition
):
    alice = create_user(admin_client, "alice", display_name="爱丽丝")
    bob = create_user(admin_client, "bob", display_name="鲍勃")
    alice_client = logged_in_client(auth_app, "alice")
    bob_client = logged_in_client(auth_app, "bob")
    bank_png = png(tmp_path / "uploads", "ChatGPT-202603-银行交易.png")
    fake_recognition.set(bank_png.name, chatgpt_bank())
    first = upload(alice_client, bank_png)
    expense_id = confirm(alice_client, first, payload(first["groups"][0]))["created"][0]
    order_png = png(tmp_path / "uploads", "ChatGPT-202603-订单.png")
    fake_recognition.set(order_png.name, chatgpt_order())
    second = upload(bob_client, order_png)

    confirm(bob_client, second, payload(second["groups"][0], "attach", expense_id=expense_id))

    timeline = detail(admin_client, expense_id)["timeline"]
    assert [event["to_status"] for event in timeline] == ["spent", "invoiced", "complete"]
    assert [event["actor"] for event in timeline] == [ref(alice), ref(alice), ref(bob)]


def test_manual_status_and_deactivated_user_name_kept(auth_app, admin_client):
    carol = create_user(admin_client, "carol", display_name="卡罗尔")
    carol_client = logged_in_client(auth_app, "carol")
    body = {"spent_on": "2026-09-01", "amount_cents": 1000, "merchant": "文具店"}
    expense_id = carol_client.post("/api/expenses", json=body).json()["data"]["id"]
    admin_client.post(f"/api/expenses/{expense_id}/status", json={"status": "void", "note": "重复"})
    admin_client.patch(f"/api/users/{carol['id']}", json={"is_active": False})

    timeline = detail(admin_client, expense_id)["timeline"]

    assert [event["actor"] for event in timeline] == [
        ref(carol),
        {"id": 1, "display_name": "管理员"},
    ]


def test_batch_and_export_record_creator(auth_app, admin_client):
    dave = create_user(admin_client, "dave", display_name="戴夫")
    dave_client = logged_in_client(auth_app, "dave")
    body = {"spent_on": "2026-09-01", "amount_cents": 1000, "merchant": "文具店"}
    expense_id = dave_client.post("/api/expenses", json=body).json()["data"]["id"]
    batch = dave_client.post("/api/batches", json={"name": "九月"}).json()["data"]
    admin_client.post(
        f"/api/batches/{batch['id']}/items", json={"add": [expense_id], "force": True}
    )

    response = admin_client.post(f"/api/batches/{batch['id']}/export", json={"layout": "by_kind"})

    assert batch["created_by"] == ref(dave)
    assert response.json()["data"]["created_by"] == {"id": 1, "display_name": "管理员"}
    batch_detail = dave_client.get(f"/api/batches/{batch['id']}").json()["data"]
    assert batch_detail["created_by"] == ref(dave)
    assert batch_detail["exports"][0]["created_by"] == {"id": 1, "display_name": "管理员"}


def test_inbox_attachments_have_no_uploader(auth_app, auth_settings, admin_client):
    auth_settings.inbox_dir.mkdir(parents=True, exist_ok=True)
    source = FIXTURES_DIR / "invoices" / "not_invoice.pdf"
    shutil.copyfile(source, auth_settings.inbox_dir / "not_invoice.pdf")

    with acting_as(1):  # 收件箱线程不继承请求上下文
        worker = threading.Thread(target=process_inbox_once, args=(auth_app, 0))
        worker.start()
        worker.join()

    with auth_app.state.session_factory() as db:
        attachment = db.scalar(select(Attachment))
        assert attachment.uploaded_by_id is None
    unassigned = admin_client.get("/api/attachments/unassigned").json()["data"]
    assert [item["uploaded_by"] for item in unassigned] == [None]


def test_context_reaches_sync_and_async_endpoints(auth_app, admin_client):
    bob = create_user(admin_client, "bob")

    @auth_app.get("/api/test/whoami-sync")
    def whoami_sync() -> dict:
        return {"user_id": current_user_id(), "thread": threading.current_thread().name}

    @auth_app.get("/api/test/whoami-async")
    async def whoami_async() -> dict:
        return {"user_id": current_user_id()}

    bob_client = logged_in_client(auth_app, "bob")
    sync = bob_client.get("/api/test/whoami-sync").json()
    assert sync["user_id"] == bob["id"]
    assert sync["thread"] != threading.current_thread().name
    assert bob_client.get("/api/test/whoami-async").json() == {"user_id": bob["id"]}
    assert admin_client.get("/api/test/whoami-sync").json()["user_id"] == 1
    assert TestClient(auth_app).get("/api/test/whoami-sync").status_code == 401
    assert current_user_id() is None
