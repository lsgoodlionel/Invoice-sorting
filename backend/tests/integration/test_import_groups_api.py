"""按凭证组导入（设计 v2.1 验收用例 V01/V02/V03/V04/V05/V07/V09）。"""

import shutil
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select

from invoice_sorting.db.models import Category, Expense
from invoice_sorting.importer import service as importer_service
from tests.conftest import FIXTURES_DIR
from tests.evidence_factory import JUNE_28, png, recognized
from tests.invoice_factory import blank_pdf, parsed_invoice

JD_ORDER_NO = "338600000001"


def upload(client, *paths: Path) -> dict:
    files = [
        ("files", (path.name, path.read_bytes(), "application/octet-stream")) for path in paths
    ]
    response = client.post("/api/imports", files=files)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def payload(group: dict, action: str = "create", **overrides) -> dict:
    ids = [attachment["id"] for attachment in group["attachments"]]
    return {
        "group_id": group["group_id"],
        "attachment_ids": ids,
        "action": action,
        **group["summary"],
        **overrides,
    }


def confirm(client, data: dict, *groups: dict) -> dict:
    url = f"/api/imports/{data['session_id']}/confirm"
    response = client.post(url, json={"groups": list(groups)})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def detail(client, expense_id: int) -> dict:
    return client.get(f"/api/expenses/{expense_id}").json()["data"]


def checklist(expense: dict) -> dict[str, tuple[str, str]]:
    return {i["attachment_kind"]: (i["level"], i["state"]) for i in expense["checklist"]}


def category_id(session, name: str) -> int:
    return session.scalar(select(Category.id).where(Category.name == name))


def jd_invoice(tmp_path: Path, name: str = "办公-转接头-发票.pdf") -> Path:
    target = tmp_path / "uploads" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURES_DIR / "invoices" / "jd_spaced_labels.pdf", target)
    return target


def jd_order(**fields):
    base = {
        "order_no": "3386 0000 0001",
        "amount_cents": 1290,
        "cny_cents": 1290,
        "occurred_on": date(2025, 10, 1),
        "merchant": "京东",
        "item_name": "转接头",
    }
    return recognized("order", recognizer="jd_order", **{**base, **fields})


def test_v01_invoice_and_order_screenshot_become_one_expense(
    client, session, tmp_path, fake_recognition
):
    order_png = png(tmp_path / "uploads", "办公-转接头-交易订单.png")
    fake_recognition.set(order_png.name, jd_order(), category="办公")

    data = upload(client, jd_invoice(tmp_path), order_png)

    assert len(data["groups"]) == 1
    group = data["groups"][0]
    assert group["link_reasons"] == ["订单号一致"]
    assert [a["kind"] for a in group["attachments"]] == ["invoice", "order"]
    assert group["attachments"][1]["evidence"]["order_no"] == "3386 0000 0001"
    summary = group["summary"]
    assert (summary["amount_cents"], summary["merchant"]) == (1290, "北京示例贸易有限公司")
    assert summary["is_online"] is True and summary["invoice_exempt"] is False
    assert summary["category_id"] == category_id(session, "办公用品")
    assert group["suggested_action"] == "create"

    result = confirm(client, data, payload(group))

    expense = detail(client, result["created"][0])
    assert sorted(a["kind"] for a in expense["attachments"]) == ["invoice", "order"]
    evidence = next(a["evidence"] for a in expense["attachments"] if a["kind"] == "order")
    assert evidence["confirmed"] is True
    assert checklist(expense)["order"][1] == "present"


def claude_order(**fields):
    base = {
        "order_no": "MSD8X2",
        "amount_cents": 2000,
        "currency": "USD",
        "occurred_on": JUNE_28,
        "merchant": "Apple",
        "item_name": "Claude Pro - Monthly",
        "is_foreign": True,
    }
    return recognized("order", recognizer="app_store_order", **{**base, **fields})


def apple_bank(**fields):
    base = {
        "amount_cents": 2000,
        "currency": "USD",
        "cny_cents": 14426,
        "occurred_on": JUNE_28,
        "merchant": "PP*APPLE.COM/BILL",
        "card_last4": "6411",
        "is_foreign": True,
    }
    return recognized("payment", recognizer="bank_transaction", **{**base, **fields})


def test_v02_foreign_order_and_bank_transaction_become_exempt_expense(
    client, session, tmp_path, fake_recognition
):
    order_png = png(tmp_path / "uploads", "软件-Claude Pro-202606-订单.png")
    bank_png = png(tmp_path / "uploads", "软件-Claude Pro-202606-银行交易.png")
    fake_recognition.set(order_png.name, claude_order(), category="软件")
    fake_recognition.set(bank_png.name, apple_bank(), category="软件")

    data = upload(client, order_png, bank_png)

    group = data["groups"][0]
    assert len(data["groups"]) == 1
    assert group["link_reasons"] == ["境外订单与银行交易日期一致"]
    assert [a["kind"] for a in group["attachments"]] == ["order", "payment"]
    assert group["summary"] == {
        "spent_on": "2026-06-28",
        "amount_cents": 14426,
        "currency": "USD",
        "original_amount_cents": 2000,
        "merchant": "Apple",
        "summary": "Claude Pro - Monthly",
        "category_id": category_id(session, "软件服务"),
        "is_online": True,
        "invoice_exempt": True,
    }

    result = confirm(client, data, payload(group, category_id=None))

    expense = detail(client, result["created"][0])
    assert expense["invoice_exempt"] is True
    assert (expense["currency"], expense["original_amount_cents"]) == ("USD", 2000)
    items = checklist(expense)
    assert "invoice" not in items
    assert items["order"] == ("required", "present") and items["payment"] == ("required", "present")
    assert items["statement"] == ("suggested", "missing")
    assert expense["status"] == "complete" and expense["missing_count"] == 0


def chatgpt_bank():
    return recognized(
        "payment",
        amount_cents=2000,
        currency="USD",
        cny_cents=14500,
        occurred_on=date(2026, 3, 5),
        merchant="OPENAI *CHATGPT SUBSCR",
        is_foreign=True,
    )


def test_v03_v04_bank_first_then_order_suggests_attach(client, tmp_path, fake_recognition):
    bank_png = png(tmp_path / "uploads", "ChatGPT-202603-银行交易.png")
    fake_recognition.set(bank_png.name, chatgpt_bank())
    first = upload(client, bank_png)
    group = first["groups"][0]
    assert group["summary"]["invoice_exempt"] is True and group["suggested_action"] == "create"
    expense_id = confirm(client, first, payload(group))["created"][0]
    created = detail(client, expense_id)
    assert checklist(created)["order"] == ("required", "missing")
    assert created["status"] == "invoiced"

    order_png = png(tmp_path / "uploads", "ChatGPT-202603-订单.png")
    fake_recognition.set(
        order_png.name,
        recognized(
            "order",
            amount_cents=2000,
            currency="USD",
            occurred_on=date(2026, 3, 5),
            merchant="OpenAI",
            item_name="ChatGPT Plus",
            is_foreign=True,
        ),
    )
    second = upload(client, order_png)

    group = second["groups"][0]
    assert group["suggested_action"] == "attach"
    assert group["match"]["expense_id"] == expense_id
    assert group["match"]["reasons"] == ["原币金额相同", "日期相同", "商家相同", "正好缺少订单明细"]
    assert group["match"]["missing_kinds"] == ["order"]
    result = confirm(client, second, payload(group, "attach", expense_id=expense_id))
    assert result == {"created": [], "attached": [expense_id], "skipped": 0}
    assert detail(client, expense_id)["status"] == "complete"


def test_v05_order_screenshot_after_invoice_matches_by_order_no(
    client, session, tmp_path, fake_recognition
):
    first = upload(client, jd_invoice(tmp_path))
    expense_id = confirm(client, first, payload(first["groups"][0]))["created"][0]
    order_png = png(tmp_path / "uploads", "订单截图.png")
    fake_recognition.set(order_png.name, recognized("order", order_no=JD_ORDER_NO))

    data = upload(client, order_png)

    group = data["groups"][0]
    assert group["match"]["expense_id"] == expense_id
    assert group["match"]["reasons"] == ["订单号一致"] and group["match"]["score"] == 100
    assert group["suggested_action"] == "attach" and group["warnings"] == []
    confirm(client, data, payload(group, "attach", expense_id=expense_id))

    again = png(tmp_path / "uploads", "订单截图-再次.png")
    fake_recognition.set(again.name, recognized("order", order_no=JD_ORDER_NO))
    duplicate = upload(client, again)["groups"][0]

    assert duplicate["warnings"] == [f"可能重复：该订单的订单截图已在记录 #{expense_id}"]
    assert duplicate["suggested_action"] == "skip"
    assert session.scalar(select(func.count(Expense.id))) == 1


@pytest.fixture
def taxi_invoice(monkeypatch):
    parsed = parsed_invoice(
        invoice_no="26312000000000004680",
        issued_on=date(2026, 9, 1),
        total_cents=4680,
        seller_name="滴滴出行科技有限公司",
        item_summary="运输服务",
        tax_category="运输服务",
        region_name="上海",
    )
    monkeypatch.setattr(
        importer_service,
        "parse_invoice_file",
        lambda path: parsed if path.name == "0.pdf" else None,
    )


def test_v09_taxi_invoice_and_itinerary_grouped_by_file_key(
    client, session, tmp_path, fake_recognition, taxi_invoice
):
    invoice_pdf = blank_pdf(tmp_path / "uploads", "打车-20260901-发票.pdf")
    itinerary_pdf = blank_pdf(tmp_path / "uploads", "打车-20260901-行程单.pdf")
    fake_recognition.set(
        invoice_pdf.name, recognized("unknown"), key="打车20260901", category="打车"
    )
    fake_recognition.set(
        itinerary_pdf.name,
        recognized(
            "itinerary",
            amount_cents=4680,
            cny_cents=4680,
            occurred_on=date(2026, 9, 1),
            merchant="滴滴出行",
        ),
        key="打车20260901",
    )

    data = upload(client, invoice_pdf, itinerary_pdf)

    group = data["groups"][0]
    assert len(data["groups"]) == 1
    assert group["link_reasons"] == ["文件名一致"]
    assert [a["kind"] for a in group["attachments"]] == ["invoice", "itinerary"]
    assert [a["file_key"] for a in group["attachments"]] == ["打车20260901"] * 2
    assert group["summary"]["category_id"] == category_id(session, "差旅交通")
    expense = detail(client, confirm(client, data, payload(group))["created"][0])
    assert checklist(expense)["itinerary"] == ("required", "present")


def test_unrecognized_screenshot_is_single_skip_group(client, tmp_path, fake_recognition):
    data = upload(client, png(tmp_path / "uploads", "随手截图.png"))

    group = data["groups"][0]
    assert group["suggested_action"] == "skip" and group["summary"]["amount_cents"] is None
    assert group["attachments"][0]["kind"] == "other"
    assert fake_recognition.calls == ["随手截图.png"]
    assert confirm(client, data, payload(group, "skip")) == {
        "created": [],
        "attached": [],
        "skipped": 1,
    }
