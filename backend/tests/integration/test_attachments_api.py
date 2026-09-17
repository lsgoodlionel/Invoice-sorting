"""附件 API：待归属、文件流、缩略图、改类型/归属、删除、购方抬头校验。"""

import io
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from PIL import Image

from invoice_sorting.attachments.storage import store_file
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.db.models import InvoiceData


def png_bytes(color: str = "red", size: tuple[int, int] = (960, 480)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def create(client, **overrides) -> dict:
    payload = {"spent_on": "2026-09-15", "amount_cents": 96000, "merchant": "京东"}
    payload.update(overrides)
    return client.post("/api/expenses", json=payload).json()["data"]


@pytest.fixture
def stored(app, settings, tmp_path):
    """直接用服务层入库几份待归属文件，返回 {name: attachment_id}。"""
    pdf_path = tmp_path / "发票.pdf"
    doc = pdfium.PdfDocument.new()
    doc.new_page(300, 600)
    doc.save(str(pdf_path))
    png_path = tmp_path / "订单.png"
    png_path.write_bytes(png_bytes())
    xml_path = tmp_path / "发票.xml"
    xml_path.write_text("<?xml version='1.0'?><Invoice/>", encoding="utf-8")
    with app.state.session_factory() as session:
        pdf = store_file(session, settings, pdf_path, "发票.pdf", AttachmentKind.INVOICE)
        pdf.invoice_data = InvoiceData(
            invoice_no="24312000000012345678",
            buyer_name="某某大学",
            buyer_tax_id="12100000",
            seller_name="京东",
            confirmed=True,
        )
        png = store_file(session, settings, png_path, "订单.png", AttachmentKind.ORDER)
        xml = store_file(session, settings, xml_path, "发票.xml", AttachmentKind.OTHER)
        session.commit()
        return {"pdf": pdf.id, "png": png.id, "xml": xml.id}


def test_unassigned_lists_attachment_shape(client, stored):
    items = client.get("/api/attachments/unassigned").json()["data"]
    assert {item["id"] for item in items} == set(stored.values())
    pdf = next(item for item in items if item["id"] == stored["pdf"])
    assert pdf["kind_label"] == "发票"
    assert pdf["url"] == f"/api/attachments/{stored['pdf']}/file"
    assert pdf["file_name"].endswith(".pdf")
    assert pdf["invoice"]["invoice_no"] == "24312000000012345678"
    assert pdf["invoice"]["buyer_mismatch"] is False  # 未设置抬头时不提示


def test_buyer_mismatch_flag_uses_settings(client, stored):
    client.put("/api/settings", json={"buyer_name": "另一所大学"})
    items = client.get("/api/attachments/unassigned").json()["data"]
    pdf = next(item for item in items if item["id"] == stored["pdf"])
    assert pdf["invoice"]["buyer_mismatch"] is True

    client.put("/api/settings", json={"buyer_name": "某某大学", "buyer_tax_id": "12100000"})
    items = client.get("/api/attachments/unassigned").json()["data"]
    pdf = next(item for item in items if item["id"] == stored["pdf"])
    assert pdf["invoice"]["buyer_mismatch"] is False


def test_file_endpoint_streams_inline(client, stored):
    response = client.get(f"/api/attachments/{stored['png']}/file")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-disposition"].startswith("inline")
    assert response.content == png_bytes()
    assert client.get("/api/attachments/999/file").status_code == 404


@pytest.mark.parametrize("key", ["pdf", "png"])
def test_thumbnail_is_png_and_cached(client, settings, stored, key):
    response = client.get(f"/api/attachments/{stored[key]}/thumbnail")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    image = Image.open(io.BytesIO(response.content))
    assert max(image.size) == 480
    assert any((settings.data_dir / ".thumbs").glob("*.png"))
    assert client.get(f"/api/attachments/{stored[key]}/thumbnail").content == response.content


def test_thumbnail_unsupported_type_is_404(client, stored):
    assert client.get(f"/api/attachments/{stored['xml']}/thumbnail").status_code == 404


def test_patch_assigns_changes_kind_and_unassigns(client, settings, stored):
    expense = create(client)
    response = client.patch(
        f"/api/attachments/{stored['png']}", json={"expense_id": expense["id"], "kind": "payment"}
    )
    assert response.status_code == 200, response.text
    attachment = response.json()["data"]
    assert attachment["expense_id"] == expense["id"]
    assert attachment["kind"] == "payment"
    assert attachment["file_name"] == "支付记录_1.png"
    detail = client.get(f"/api/expenses/{expense['id']}").json()["data"]
    assert detail["attachment_count"] == 1
    assert client.get(attachment["url"]).status_code == 200

    back = client.patch(f"/api/attachments/{stored['png']}", json={"expense_id": None}).json()
    assert back["data"]["expense_id"] is None
    assert client.get(back["data"]["url"]).status_code == 200
    assert client.get(f"/api/expenses/{expense['id']}").json()["data"]["attachment_count"] == 0


def test_patch_assigning_confirmed_invoice_updates_status(client, stored):
    expense = create(client)
    client.patch(f"/api/attachments/{stored['pdf']}", json={"expense_id": expense["id"]})
    detail = client.get(f"/api/expenses/{expense['id']}").json()["data"]
    assert detail["status"] == "complete"  # 无分类时仅需发票，直接跳到凭证齐全
    assert detail["invoice_no"] == "24312000000012345678"
    assert detail["attachments"][0]["file_name"] == "发票_24312000000012345678.pdf"


def test_patch_validation(client, stored):
    url = f"/api/attachments/{stored['png']}"
    assert client.patch(url, json={"kind": "bad"}).status_code == 422
    assert client.patch(url, json={"expense_id": 999}).status_code == 404
    assert client.patch("/api/attachments/999", json={"kind": "order"}).status_code == 404


def test_delete_moves_to_trash(client, settings, stored):
    assert client.delete(f"/api/attachments/{stored['png']}").json()["data"] is None
    ids = {item["id"] for item in client.get("/api/attachments/unassigned").json()["data"]}
    assert stored["png"] not in ids
    assert any(Path(settings.trash_dir).glob("*.png"))
    assert client.delete(f"/api/attachments/{stored['png']}").status_code == 404
