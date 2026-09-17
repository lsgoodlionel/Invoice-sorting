"""免发票记录字段、清单行拖放补传自动识别（V11）、非发票凭证重新识别、文件名键回填。"""

import shutil

from sqlalchemy import select

from invoice_sorting.attachments.file_keys import backfill_file_keys
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.db.models import Attachment
from tests.conftest import FIXTURES_DIR
from tests.evidence_factory import png, recognized
from tests.invoice_factory import store_invoice

EXEMPT = {
    "spent_on": "2026-06-28",
    "amount_cents": 14426,
    "merchant": "Apple",
    "invoice_exempt": True,
    "currency": "usd",
    "original_amount_cents": 2000,
}


def create(client, **fields) -> dict:
    response = client.post("/api/expenses", json={**EXEMPT, **fields})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def upload(client, expense_id: int, *paths, kind: str | None = None) -> dict:
    files = [
        ("files", (path.name, path.read_bytes(), "application/octet-stream")) for path in paths
    ]
    data = {"kind": kind} if kind else {}
    response = client.post(f"/api/expenses/{expense_id}/attachments", files=files, data=data)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def kinds(detail: dict) -> dict[str, str]:
    return {item["attachment_kind"]: item["state"] for item in detail["checklist"]}


def test_exempt_fields_on_create_patch_and_list(client):
    detail = create(client)

    assert (detail["invoice_exempt"], detail["currency"], detail["original_amount_cents"]) == (
        True,
        "USD",
        2000,
    )
    assert "invoice" not in kinds(detail) and kinds(detail)["order"] == "missing"
    assert detail["status"] == "spent"
    row = client.get("/api/expenses").json()["data"]["items"][0]
    assert (row["invoice_exempt"], row["currency"], row["original_amount_cents"]) == (
        True,
        "USD",
        2000,
    )

    patched = client.patch(
        f"/api/expenses/{detail['id']}", json={"invoice_exempt": False, "currency": "CNY"}
    ).json()["data"]

    assert (patched["currency"], patched["original_amount_cents"]) == ("CNY", None)
    assert kinds(patched)["invoice"] == "missing"


def test_invalid_currency_and_null_flags_rejected(client):
    detail = create(client)
    bad_currency = client.post("/api/expenses", json={**EXEMPT, "currency": "美元"})
    null_flag = client.patch(f"/api/expenses/{detail['id']}", json={"invoice_exempt": None})

    assert bad_currency.status_code == 422
    assert null_flag.status_code == 422


def test_v11_dropped_payment_screenshot_is_recognized(client, tmp_path, fake_recognition):
    detail = create(client)
    shot = png(tmp_path / "up", "截图1.png")
    fake_recognition.set(shot.name, recognized("payment", cny_cents=14426, is_foreign=True))

    after = upload(client, detail["id"], shot)

    attachment = after["attachments"][0]
    assert attachment["kind"] == "payment"
    assert attachment["evidence"]["cny_cents"] == 14426
    assert attachment["evidence"]["confirmed"] is True
    assert kinds(after)["payment"] == "present"
    assert after["status"] == "invoiced"


def test_dropped_invoice_pdf_gets_invoice_data_and_explicit_kind_skips_recognition(
    client, tmp_path, fake_recognition
):
    detail = create(client, invoice_exempt=False, currency="CNY", original_amount_cents=None)
    pdf = tmp_path / "up" / "扫描件.pdf"
    pdf.parent.mkdir(parents=True)
    shutil.copyfile(FIXTURES_DIR / "invoices" / "digital_same_line.pdf", pdf)

    after = upload(client, detail["id"], pdf)
    explicit = upload(client, detail["id"], png(tmp_path / "up", "x.png"), kind="order")

    invoice = after["attachments"][0]
    assert invoice["kind"] == "invoice" and invoice["invoice"]["confirmed"] is True
    assert after["status"] == "complete"
    assert next(a for a in explicit["attachments"] if a["kind"] == "order")["evidence"] is None
    assert fake_recognition.calls == []


def test_reparse_updates_evidence_and_keeps_manual_kind(
    app, client, settings, tmp_path, fake_recognition
):
    detail = create(client)
    with app.state.session_factory() as session:
        pending = store_invoice(
            session, settings, tmp_path, name="p.pdf", kind=AttachmentKind.OTHER
        )
        session.commit()
        pending_id = pending.id
    kept = upload(client, detail["id"], png(tmp_path / "up", "o.png"), kind="order")
    kept_id = kept["attachments"][0]["id"]
    fake_recognition.set("p.pdf", recognized("payment", merchant="PP*APPLE.COM", cny_cents=1))
    fake_recognition.set("o.png", recognized("payment", merchant="Apple"), key="键值很长")

    items = client.post("/api/attachments/reparse", json={"ids": [pending_id, kept_id]}).json()

    first, second = items["data"]
    assert first["kind"] == "payment" and first["evidence"]["merchant"] == "PP*APPLE.COM"
    assert second["kind"] == "order" and second["evidence"]["doc_type"] == "payment"
    assert second["evidence"]["confirmed"] is False and second["file_key"] == "键值很长"


def test_backfill_file_keys_is_idempotent(session, settings, tmp_path, fake_recognition):
    first = store_invoice(session, settings, tmp_path, name="打车-20260901-发票.pdf")
    second = store_invoice(session, settings, tmp_path, name="已有.pdf")
    second.file_key = "保留原键值"
    third = store_invoice(session, settings, tmp_path, name="无键.pdf")
    session.commit()
    fake_recognition.keys.update({"打车-20260901-发票.pdf": "打车20260901", "已有.pdf": "新键"})

    assert backfill_file_keys(session) == 1
    assert backfill_file_keys(session) == 0

    keys = dict(session.execute(select(Attachment.id, Attachment.file_key)).all())
    assert keys == {first.id: "打车20260901", second.id: "保留原键值", third.id: ""}


def test_backfill_survives_key_errors(session, settings, tmp_path, monkeypatch):
    from invoice_sorting.attachments import file_keys

    store_invoice(session, settings, tmp_path, name="a.pdf")
    session.commit()
    monkeypatch.setattr(file_keys, "file_key", lambda _name: (_ for _ in ()).throw(ValueError()))

    assert backfill_file_keys(session) == 0  # 计算失败只记日志，不抛出
