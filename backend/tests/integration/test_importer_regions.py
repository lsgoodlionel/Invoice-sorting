"""导入：写入开票地区/订单号/税收分类，建议 is_online，外地发票提示；确认与收件箱写入 is_online。"""

import shutil

import pytest
from sqlalchemy import select

from invoice_sorting.db.models import Expense
from invoice_sorting.importer import service as importer_service
from invoice_sorting.importer.suggestions import is_online_purchase
from invoice_sorting.importer.watcher import process_inbox_once
from tests.invoice_factory import blank_pdf, parsed_invoice


@pytest.fixture(autouse=True)
def _isolate_recognition(fake_recognition):
    """凭证识别使用可控的假实现。"""


NONLOCAL_WARNING = "外地发票（北京）：需附网购订单截图，已带明细平台可免"


@pytest.fixture
def parse_as(monkeypatch):
    def install(parsed):
        monkeypatch.setattr(importer_service, "parse_invoice_file", lambda _path: parsed)

    return install


def upload(client, tmp_path) -> dict:
    path = blank_pdf(tmp_path / "uploads")
    files = [("files", (path.name, path.read_bytes(), "application/pdf"))]
    response = client.post("/api/imports", files=files)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def confirm_create(client, data: dict, **extra):
    group = data["groups"][0]
    summary = group["summary"]
    payload = {
        "group_id": group["group_id"],
        "attachment_ids": [attachment["id"] for attachment in group["attachments"]],
        "action": "create",
        "spent_on": summary["spent_on"],
        "amount_cents": summary["amount_cents"],
        "merchant": summary["merchant"],
        **extra,
    }
    response = client.post(f"/api/imports/{data['session_id']}/confirm", json={"groups": [payload]})
    assert response.status_code == 200, response.text
    return response.json()["data"]["created"][0]


def test_nonlocal_invoice_fields_and_warning(client, tmp_path, parse_as):
    parse_as(parsed_invoice())

    row = upload(client, tmp_path)["groups"][0]

    invoice = row["attachments"][0]["invoice"]
    assert invoice["region_name"] == "北京" and invoice["is_nonlocal"] is True
    assert invoice["tax_category"] == "纸制品"
    assert invoice["order_no"] == "" and invoice["detail_platform"] is False
    assert row["summary"]["is_online"] is False
    assert NONLOCAL_WARNING in row["warnings"]


def test_platform_invoice_with_order_no_is_online_without_warning(client, tmp_path, parse_as):
    parse_as(parsed_invoice(seller_name="北京京东世纪贸易有限公司", order_no="338623377834"))

    row = upload(client, tmp_path)["groups"][0]

    invoice = row["attachments"][0]["invoice"]
    assert invoice["order_no"] == "338623377834" and invoice["detail_platform"] is True
    assert row["summary"]["is_online"] is True
    assert not any("外地发票" in warning for warning in row["warnings"])


def test_local_invoice_has_no_warning(client, tmp_path, parse_as):
    parse_as(parsed_invoice(region_name="上海", region_code="31"))

    row = upload(client, tmp_path)["groups"][0]

    assert row["attachments"][0]["invoice"]["is_nonlocal"] is False
    assert not any("外地发票" in warning for warning in row["warnings"])


def test_warning_follows_local_region_setting(client, tmp_path, parse_as):
    client.put("/api/settings", json={"local_region": "北京"})
    parse_as(parsed_invoice())

    row = upload(client, tmp_path)["groups"][0]

    assert row["attachments"][0]["invoice"]["is_nonlocal"] is False
    assert NONLOCAL_WARNING not in row["warnings"]


@pytest.mark.parametrize(
    ("order_no", "seller", "expected"),
    [
        ("123", "某文具店", True),
        ("", "浙江天猫网络有限公司", True),
        ("", "拼多多（上海）网络科技有限公司", True),
        ("  ", "某文具店", False),
        ("", "", False),
    ],
)
def test_is_online_purchase(order_no, seller, expected):
    assert is_online_purchase(order_no, seller) is expected


def test_confirm_create_writes_is_online(client, tmp_path, parse_as):
    parse_as(parsed_invoice(order_no="1"))
    created = confirm_create(client, upload(client, tmp_path), is_online=True)
    detail = client.get(f"/api/expenses/{created}").json()["data"]
    assert detail["is_online"] is True
    assert detail["region_name"] == "北京" and detail["is_nonlocal"] is True
    assert "order" in {item["attachment_kind"] for item in detail["checklist"]}

    parse_as(parsed_invoice(invoice_no="26112000000000000002"))
    plain = confirm_create(client, upload(client, tmp_path))
    assert client.get(f"/api/expenses/{plain}").json()["data"]["is_online"] is False


def test_inbox_auto_confirm_writes_is_online(app, session, settings, tmp_path, parse_as):
    parse_as(parsed_invoice(seller_name="上海圆迈贸易有限公司", region_name="上海"))
    settings.inbox_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(blank_pdf(tmp_path / "src"), settings.inbox_dir / "发票.pdf")

    assert process_inbox_once(app, interval=0) == 1

    expense = session.scalar(select(Expense))
    assert expense is not None and expense.is_online is True
    invoice = expense.attachments[0].invoice_data
    assert (invoice.region_name, invoice.tax_category) == ("上海", "纸制品")
