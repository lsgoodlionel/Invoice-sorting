"""重新识别发票：更新票面字段、保留 confirmed、补商家名、号码冲突保留原号、解析失败不变。"""

from datetime import date

import pytest

from invoice_sorting.attachments import reparse
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.db.models import Attachment, Expense
from invoice_sorting.expenses.service import create_expense, refresh_expense
from tests.invoice_factory import parsed_invoice, store_invoice


@pytest.fixture(autouse=True)
def _isolate_recognition(fake_recognition):
    """凭证识别使用可控的假实现。"""


URL = "/api/attachments/reparse"
OLD_NO = "26312000000000000099"


@pytest.fixture
def parse_as(monkeypatch):
    calls: list[str] = []

    def install(result, probably_invoice: bool = False):
        def fake_parse(path):
            calls.append(path.name)
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(reparse, "parse_invoice_file", fake_parse)
        monkeypatch.setattr(reparse, "is_probably_invoice", lambda _path: probably_invoice)

    install.calls = calls
    return install


def post(client, ids: list[int]) -> list[dict]:
    response = client.post(URL, json={"ids": ids})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def add_invoice(session, settings, tmp_path, expense=None, **invoice) -> int:
    data = {"invoice_no": OLD_NO, "seller_name": "", "total_cents": 100, **invoice}
    attachment = store_invoice(session, settings, tmp_path, invoice=data, expense=expense)
    if expense is not None:
        refresh_expense(session, settings, expense)
    session.commit()
    return attachment.id


def blank_expense(session, settings, merchant: str = "") -> Expense:
    return create_expense(
        session, settings, spent_on=date(2026, 9, 1), amount_cents=500, merchant=merchant
    )


def test_updates_fields_keeps_confirmed_and_fills_merchant(
    client, session, settings, tmp_path, parse_as
):
    expense = blank_expense(session, settings)
    attachment_id = add_invoice(session, settings, tmp_path, expense, confirmed=True)
    parse_as(parsed_invoice())

    items = post(client, [attachment_id])

    invoice = items[0]["invoice"]
    assert invoice["confirmed"] is True
    assert invoice["invoice_no"] == "26112000000000000001"
    assert (invoice["seller_name"], invoice["region_name"], invoice["total_cents"]) == (
        "北京文具商行有限公司",
        "北京",
        12800,
    )
    assert invoice["tax_category"] == "纸制品" and invoice["is_nonlocal"] is True
    assert items[0]["file_name"] == "发票_26112000000000000001.pdf"
    detail = client.get(f"/api/expenses/{expense.id}").json()["data"]
    assert detail["merchant"] == "北京文具商行有限公司" and detail["amount_cents"] == 500
    assert "order" in {item["attachment_kind"] for item in detail["checklist"]}


def test_existing_merchant_is_not_overwritten(client, session, settings, tmp_path, parse_as):
    expense = blank_expense(session, settings, merchant="我的商家")
    attachment_id = add_invoice(session, settings, tmp_path, expense)
    parse_as(parsed_invoice())

    post(client, [attachment_id])

    assert client.get(f"/api/expenses/{expense.id}").json()["data"]["merchant"] == "我的商家"


def test_conflicting_invoice_no_keeps_original(client, session, settings, tmp_path, parse_as):
    add_invoice(session, settings, tmp_path, invoice_no="26112000000000000001")
    target = add_invoice(session, settings, tmp_path)
    parse_as(parsed_invoice(seller_name="新销售方"))

    items = post(client, [target])

    assert items[0]["invoice"]["invoice_no"] == OLD_NO
    assert items[0]["invoice"]["seller_name"] == "新销售方"


def test_missing_parsed_number_keeps_original(client, session, settings, tmp_path, parse_as):
    target = add_invoice(session, settings, tmp_path)
    parse_as(parsed_invoice(invoice_no=None))
    assert post(client, [target])[0]["invoice"]["invoice_no"] == OLD_NO


@pytest.mark.parametrize("result", [None, RuntimeError("坏文件")])
def test_parse_failure_leaves_attachment_unchanged(
    client, session, settings, tmp_path, parse_as, result
):
    target = add_invoice(session, settings, tmp_path, seller_name="原销售方")
    parse_as(result)

    items = post(client, [target])

    assert items[0]["invoice"]["seller_name"] == "原销售方"
    assert items[0]["invoice"]["invoice_no"] == OLD_NO


def test_non_invoice_that_looks_like_invoice_gets_invoice_data(
    client, app, settings, tmp_path, parse_as
):
    with app.state.session_factory() as session:
        other = store_invoice(
            session, settings, tmp_path, name="扫描.pdf", kind=AttachmentKind.OTHER
        )
        order = store_invoice(
            session, settings, tmp_path, name="订单.pdf", kind=AttachmentKind.ORDER
        )
        session.commit()
        ids = [other.id, order.id]
    parse_as(parsed_invoice(), probably_invoice=True)

    items = post(client, ids)

    assert items[0]["kind"] == "invoice" and items[0]["invoice"]["confirmed"] is False
    assert items[0]["invoice"]["region_name"] == "北京"
    with app.state.session_factory() as session:
        assert session.get(Attachment, ids[0]).invoice_data is not None


def test_order_that_does_not_look_like_invoice_is_not_parsed(
    client, app, settings, tmp_path, parse_as
):
    with app.state.session_factory() as session:
        order = store_invoice(
            session, settings, tmp_path, name="订单.pdf", kind=AttachmentKind.ORDER
        )
        session.commit()
        order_id = order.id
    parse_as(parsed_invoice(), probably_invoice=False)

    items = post(client, [order_id])

    assert items[0]["kind"] == "order" and items[0]["invoice"] is None
    assert parse_as.calls == []


def test_missing_file_is_skipped(client, session, settings, tmp_path, parse_as):
    target = add_invoice(session, settings, tmp_path, seller_name="原销售方")
    (settings.data_dir / session.get(Attachment, target).file_path).unlink()
    parse_as(parsed_invoice())

    assert post(client, [target])[0]["invoice"]["seller_name"] == "原销售方"
    assert parse_as.calls == []


def test_attached_non_invoice_becomes_confirmed_invoice(
    client, session, settings, tmp_path, parse_as
):

    expense = blank_expense(session, settings, merchant="店")
    attachment = store_invoice(
        session, settings, tmp_path, name="扫描.pdf", kind=AttachmentKind.OTHER, expense=expense
    )
    session.commit()
    parse_as(parsed_invoice(), probably_invoice=True)

    items = post(client, [attachment.id])

    assert items[0]["kind"] == "invoice" and items[0]["invoice"]["confirmed"] is True
    assert client.get(f"/api/expenses/{expense.id}").json()["data"]["status"] != "spent"
