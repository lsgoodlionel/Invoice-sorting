"""按最新规则重新分类：预览分错的记录（如图书被分到印刷快递/易耗品），管理员确认后批量改正。"""

from datetime import date

from sqlalchemy import select

from invoice_sorting.db.models import Category, Expense, ItemMemory
from invoice_sorting.expenses.service import create_expense
from tests.invoice_factory import store_invoice


def category_id(session, name: str) -> int:
    return session.scalar(select(Category.id).where(Category.name == name))


def book_expense(session, settings, tmp_path, *, category: str, name: str, status: str = "spent"):
    expense = create_expense(
        session,
        settings,
        spent_on=date(2025, 8, 15),
        amount_cents=5971,
        merchant="上海圆迈贸易有限公司",
        summary="系统之美",
        category_id=category_id(session, category),
    )
    store_invoice(
        session,
        settings,
        tmp_path,
        name=name,
        expense=expense,
        invoice={
            "invoice_no": f"2531700000190007{expense.id:04d}",
            "seller_name": "上海圆迈贸易有限公司",
            "item_summary": "系统之美",
            "tax_category": "印刷品",
            "confirmed": True,
        },
    )
    expense.status = status
    session.commit()
    return expense


def test_preview_lists_misclassified_books_with_basis(client, session, settings, tmp_path):
    wrong = book_expense(session, settings, tmp_path, category="印刷快递", name="a.pdf")
    right = book_expense(session, settings, tmp_path, category="图书", name="图书-b.pdf")

    data = client.get("/api/reclassify/preview").json()["data"]

    assert [item["expense_id"] for item in data] == [wrong.id]
    item = data[0]
    assert item["current_category_name"] == "印刷快递"
    assert item["suggested_category_name"] == "图书"
    assert item["basis"] == "发票税收分类：印刷品"
    assert right.id not in [entry["expense_id"] for entry in data]


def test_preview_skips_sent_records_unless_requested(client, session, settings, tmp_path):
    sent = book_expense(session, settings, tmp_path, category="易耗品", name="c.pdf", status="sent")

    assert client.get("/api/reclassify/preview").json()["data"] == []
    included = client.get("/api/reclassify/preview?include_sent=true").json()["data"]
    assert [item["expense_id"] for item in included] == [sent.id]


def test_apply_changes_category_without_writing_memory(client, session, settings, tmp_path):
    wrong = book_expense(session, settings, tmp_path, category="易耗品", name="d.pdf")
    books = category_id(session, "图书")

    response = client.post(
        "/api/reclassify/apply", json={"changes": [{"expense_id": wrong.id, "category_id": books}]}
    )

    assert response.json()["data"] == {"updated": 1}
    session.expire_all()
    assert session.get(Expense, wrong.id).category_id == books
    assert session.scalars(select(ItemMemory)).all() == []
    detail = client.get(f"/api/expenses/{wrong.id}").json()["data"]
    assert any(item["attachment_kind"] == "order" for item in detail["checklist"])


def test_apply_rejects_unknown_category(client, session, settings, tmp_path):
    wrong = book_expense(session, settings, tmp_path, category="易耗品", name="e.pdf")

    response = client.post(
        "/api/reclassify/apply", json={"changes": [{"expense_id": wrong.id, "category_id": 9999}]}
    )

    assert response.status_code == 404


def test_reclassify_requires_admin(auth_app, admin_client):
    from tests.auth_helpers import create_user, logged_in_client

    create_user(admin_client, "member1")
    member = logged_in_client(auth_app, "member1")

    assert member.get("/api/reclassify/preview").status_code == 403
    assert admin_client.get("/api/reclassify/preview").status_code == 200
