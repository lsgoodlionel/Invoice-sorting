"""待归属发票批量生成记录：新建 / 挂到已支出记录 / 跳过（含单条失败不影响其他）。"""

from datetime import date

import pytest
from sqlalchemy import func, select

from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.common.errors import AppError
from invoice_sorting.db.models import Expense
from invoice_sorting.importer import auto_confirm
from tests.invoice_factory import store_invoice


@pytest.fixture(autouse=True)
def _isolate_recognition(fake_recognition):
    """凭证识别使用可控的假实现。"""


URL = "/api/attachments/create-expenses"


def invoice(no: str, **overrides) -> dict:
    return {
        "invoice_no": no,
        "issued_on": date(2026, 9, 12),
        "total_cents": 4500,
        "seller_name": "上海文具店",
        "item_summary": "笔记本",
        "tax_category": "纸制品",
        **overrides,
    }


@pytest.fixture
def add(app, settings, tmp_path):
    def _add(invoice_data: dict | None = None, **kwargs) -> int:
        with app.state.session_factory() as session:
            attachment = store_invoice(session, settings, tmp_path, invoice=invoice_data, **kwargs)
            session.commit()
            return attachment.id

    return _add


def post(client, ids: list[int]) -> dict:
    response = client.post(URL, json={"ids": ids})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_creates_expense_from_invoice(client, add):
    attachment_id = add(invoice("1", order_no="998877", seller_name="北京京东世纪贸易有限公司"))

    result = post(client, [attachment_id])

    assert result["attached"] == [] and result["skipped"] == []
    detail = client.get(f"/api/expenses/{result['created'][0]}").json()["data"]
    assert (detail["spent_on"], detail["amount_cents"]) == ("2026-09-12", 4500)
    assert detail["merchant"] == "北京京东世纪贸易有限公司" and detail["is_online"] is True
    assert detail["category_name"] == "办公用品"
    assert detail["attachments"][0]["invoice"]["confirmed"] is True
    assert detail["status"] != "spent"


def test_attaches_to_matching_spent_expense(client, add):
    spent = client.post(
        "/api/expenses",
        json={"spent_on": "2026-09-10", "amount_cents": 4500, "merchant": "文具店"},
    ).json()["data"]
    first, second = add(invoice("1")), add(invoice("2"))

    result = post(client, [first, second])

    assert result["attached"] == [spent["id"]]
    assert len(result["created"]) == 1 and result["created"][0] != spent["id"]


def test_skips_with_reasons(client, add, session):
    assigned_expense = client.post(
        "/api/expenses", json={"spent_on": "2026-09-10", "amount_cents": 1, "merchant": "x"}
    ).json()["data"]
    no_amount = add(invoice("1", total_cents=None), name="缺金额.pdf")
    no_date = add(invoice("2", issued_on=None), name="缺日期.pdf")
    order = add(kind=AttachmentKind.ORDER, name="订单.pdf")
    empty_invoice = add(name="未识别.pdf")
    assigned = add(invoice("3"), name="已归属.pdf")
    client.patch(f"/api/attachments/{assigned}", json={"expense_id": assigned_expense["id"]})

    result = post(client, [no_amount, no_date, order, empty_invoice, assigned])

    assert result["created"] == [] and result["attached"] == []
    reasons = {item["id"]: (item["original_name"], item["reason"]) for item in result["skipped"]}
    assert reasons[no_amount] == ("缺金额.pdf", "未识别到金额，请手工处理")
    assert reasons[no_date] == ("缺日期.pdf", "未识别到开票日期，请手工处理")
    assert reasons[order] == ("订单.pdf", "未识别到金额，请手工处理")
    assert "重新识别" in reasons[empty_invoice][1]
    assert f"#{assigned_expense['id']}" in reasons[assigned][1]
    assert session.scalar(select(func.count(Expense.id))) == 1


def test_unknown_merchant_used_when_seller_missing(client, add):
    result = post(client, [add(invoice("1", seller_name=""))])
    detail = client.get(f"/api/expenses/{result['created'][0]}").json()["data"]
    assert detail["merchant"] == "未知商家"


def test_single_failure_only_skips_that_invoice(client, add, session, monkeypatch):
    broken, app_error, good = add(invoice("1")), add(invoice("2")), add(invoice("3"))
    original = auto_confirm.confirm_groups

    def flaky(session_, settings_, allowed, groups):
        attachment_id = groups[0].attachment_ids[0]
        if attachment_id == broken:
            original(session_, settings_, allowed, groups)  # 先真实写入，再失败，验证回滚
            raise RuntimeError("boom")
        if attachment_id == app_error:
            raise AppError("文件“x”：请填写商家")
        return original(session_, settings_, allowed, groups)

    monkeypatch.setattr(auto_confirm, "confirm_groups", flaky)

    result = post(client, [broken, app_error, good])

    assert len(result["created"]) == 1
    reasons = {item["id"]: item["reason"] for item in result["skipped"]}
    assert reasons == {broken: "自动生成记录失败，请手工处理", app_error: "文件“x”：请填写商家"}
    session.expire_all()
    assert session.scalar(select(func.count(Expense.id))) == 1
    unassigned = {item["id"] for item in client.get("/api/attachments/unassigned").json()["data"]}
    assert unassigned == {broken, app_error}


def test_rejects_unknown_ids(client):
    assert client.post(URL, json={"ids": [4242]}).status_code == 404
