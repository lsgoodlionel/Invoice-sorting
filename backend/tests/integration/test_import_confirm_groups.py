"""按组确认：组间移动文件与改类型、每组一张发票、会话校验、补全挂接目标、免票缺金额。

另含候选记录接口，以及“生成记录”与收件箱的分组自动确认。
"""

import shutil
from datetime import date

from sqlalchemy import func, select

from invoice_sorting.db.models import Attachment, Expense
from invoice_sorting.importer.watcher import process_inbox_once
from tests.conftest import FIXTURES_DIR
from tests.evidence_factory import png, recognized
from tests.integration.test_import_groups_api import (
    apple_bank,
    claude_order,
    confirm,
    jd_invoice,
    payload,
    upload,
)

INVOICES = FIXTURES_DIR / "invoices"


def post_confirm(client, data: dict, *groups: dict):
    return client.post(f"/api/imports/{data['session_id']}/confirm", json={"groups": list(groups)})


def ids_by_name(data: dict) -> dict[str, int]:
    return {a["original_name"]: a["id"] for g in data["groups"] for a in g["attachments"]}


def expense_count(session) -> int:
    session.expire_all()
    return session.scalar(select(func.count(Expense.id)))


def test_move_files_between_groups_and_override_kinds(client, session, tmp_path, fake_recognition):
    extra = png(tmp_path / "uploads", "a.png")
    lonely = png(tmp_path / "uploads", "b.png")
    data = upload(client, jd_invoice(tmp_path), extra, lonely)
    assert len(data["groups"]) == 3
    ids = ids_by_name(data)
    invoice_group = data["groups"][0]

    moved = payload(
        invoice_group,
        attachment_ids=[ids["办公-转接头-发票.pdf"], ids["a.png"]],
        kinds={str(ids["a.png"]): "order"},
    )
    split = {"group_id": "split-1", "attachment_ids": [ids["b.png"]], "action": "skip"}
    result = confirm(client, data, moved, split)

    assert len(result["created"]) == 1 and result["skipped"] == 1
    expense = client.get(f"/api/expenses/{result['created'][0]}").json()["data"]
    assert sorted(a["kind"] for a in expense["attachments"]) == ["invoice", "order"]
    order_file = next(a for a in expense["attachments"] if a["kind"] == "order")["file_name"]
    assert order_file.startswith("订单明细_")
    session.expire_all()
    assert session.get(Attachment, ids["b.png"]).expense_id is None
    again = post_confirm(client, data, split)
    assert again.status_code == 404


def test_group_with_two_invoices_is_rejected_and_nothing_changes(client, session, tmp_path):
    jd = jd_invoice(tmp_path)
    same_line = tmp_path / "uploads" / "digital_same_line.pdf"
    shutil.copyfile(INVOICES / "digital_same_line.pdf", same_line)
    data = upload(client, jd, same_line)
    ids = list(ids_by_name(data).values())

    response = post_confirm(client, data, payload(data["groups"][0], attachment_ids=ids))

    assert response.status_code == 400
    assert "每组最多一张发票" in response.json()["error"]
    assert expense_count(session) == 0


def test_kind_override_to_invoice_counts_and_bad_kind_key(client, tmp_path):
    data = upload(client, jd_invoice(tmp_path), png(tmp_path / "uploads", "a.png"))
    ids = list(ids_by_name(data).values())
    group = payload(data["groups"][0], attachment_ids=ids)

    two = post_confirm(client, data, {**group, "kinds": {str(ids[1]): "invoice"}})
    stray = post_confirm(client, data, {**group, "kinds": {"999": "order"}})

    assert "每组最多一张发票" in two.json()["error"]
    assert stray.json()["error"].endswith("类型设置中的附件 #999 不在该组")


def test_attachment_from_other_session_is_rejected(client, tmp_path):
    first = upload(client, png(tmp_path / "uploads", "a.png"))
    second = upload(client, png(tmp_path / "uploads", "b.png"))
    foreign_id = first["groups"][0]["attachments"][0]["id"]

    response = post_confirm(
        client, second, payload(second["groups"][0], "skip", attachment_ids=[foreign_id])
    )

    assert response.status_code == 400
    assert response.json()["error"] == "文件“a.png”：不属于本次导入或已处理"


def test_exempt_create_requires_cny_amount(client, tmp_path, fake_recognition):
    order = png(tmp_path / "uploads", "claude.png")
    fake_recognition.set(order.name, claude_order())
    data = upload(client, order)
    group = data["groups"][0]
    assert group["summary"]["invoice_exempt"] is True and group["summary"]["amount_cents"] is None
    assert group["suggested_action"] == "skip"

    response = post_confirm(client, data, payload(group))

    assert response.json()["error"] == "文件“claude.png”：请填写人民币金额"
    created = confirm(client, data, payload(group, amount_cents=14426))["created"]
    expense = client.get(f"/api/expenses/{created[0]}").json()["data"]
    assert (expense["amount_cents"], expense["original_amount_cents"]) == (14426, 2000)


def test_attach_fills_original_currency_without_touching_amount(client, tmp_path, fake_recognition):
    spent = client.post(
        "/api/expenses", json={"spent_on": "2026-06-29", "amount_cents": 14426, "merchant": "Apple"}
    ).json()["data"]
    order = png(tmp_path / "uploads", "claude.png")
    fake_recognition.set(order.name, claude_order())
    data = upload(client, order)

    confirm(client, data, payload(data["groups"][0], "attach", expense_id=spent["id"]))

    expense = client.get(f"/api/expenses/{spent['id']}").json()["data"]
    assert (expense["currency"], expense["original_amount_cents"]) == ("USD", 2000)
    assert (expense["amount_cents"], expense["spent_on"]) == (14426, "2026-06-29")


def test_candidates_endpoint(client, session, tmp_path, fake_recognition):
    spent = client.post(
        "/api/expenses", json={"spent_on": "2026-06-28", "amount_cents": 14426, "merchant": "Apple"}
    ).json()["data"]
    bank = png(tmp_path / "uploads", "bank.png")
    fake_recognition.set(bank.name, apple_bank())
    attachment_id = upload(client, bank)["groups"][0]["attachments"][0]["id"]

    candidates = client.get(f"/api/attachments/{attachment_id}/candidates").json()["data"]

    assert [c["expense_id"] for c in candidates] == [spent["id"]]
    assert candidates[0]["score"] == 90
    assert candidates[0]["reasons"] == ["金额相同", "日期相同", "商家相同"]
    client.patch(f"/api/attachments/{attachment_id}", json={"expense_id": spent["id"]})
    assert client.get(f"/api/attachments/{attachment_id}/candidates").status_code == 409
    assert client.get("/api/attachments/4242/candidates").status_code == 404


def test_create_expenses_groups_selected_attachments(client, session, tmp_path, fake_recognition):
    order, bank = png(tmp_path / "uploads", "o.png"), png(tmp_path / "uploads", "p.png")
    fake_recognition.set(order.name, claude_order())
    fake_recognition.set(bank.name, apple_bank())
    data = upload(client, order, bank)
    ids = list(ids_by_name(data).values())

    result = client.post("/api/attachments/create-expenses", json={"ids": ids}).json()["data"]

    assert len(result["created"]) == 1 and result["skipped"] == []
    expense = client.get(f"/api/expenses/{result['created'][0]}").json()["data"]
    assert expense["invoice_exempt"] is True and len(expense["attachments"]) == 2


def test_inbox_groups_files_dropped_together(app, session, settings, tmp_path, fake_recognition):
    settings.inbox_dir.mkdir(parents=True, exist_ok=True)
    for name, result in (("o.png", claude_order()), ("p.png", apple_bank())):
        fake_recognition.set(name, result)
        shutil.copyfile(png(tmp_path / "src", name), settings.inbox_dir / name)
    duplicate = recognized("order", order_no="MSD8X2")
    fake_recognition.set("dup.png", duplicate)

    assert process_inbox_once(app, interval=0) == 2

    expenses = list(session.scalars(select(Expense)))
    assert len(expenses) == 1 and expenses[0].invoice_exempt is True
    assert expenses[0].spent_on == date(2026, 6, 28) and expenses[0].amount_cents == 14426
    shutil.copyfile(png(tmp_path / "src", "dup.png"), settings.inbox_dir / "dup.png")
    assert process_inbox_once(app, interval=0) == 1
    session.expire_all()
    pending = session.scalars(select(Attachment).where(Attachment.expense_id.is_(None))).all()
    assert [item.original_name for item in pending] == ["dup.png"]
