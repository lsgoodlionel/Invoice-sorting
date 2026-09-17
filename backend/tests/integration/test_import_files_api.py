"""分文件导入：start → 逐个 files → finish → confirm（带进度的上传流程）。"""

import shutil
from datetime import date
from pathlib import Path

import pytest

from invoice_sorting.importer import service as importer_service
from tests.conftest import FIXTURES_DIR
from tests.evidence_factory import png, recognized
from tests.integration.test_import_groups_api import confirm, jd_invoice, jd_order, payload, upload
from tests.invoice_factory import blank_pdf, parsed_invoice

EXPIRED = "导入会话已过期，请重新导入"


def start(client) -> str:
    response = client.post("/api/imports/start")
    assert response.status_code == 200, response.text
    return response.json()["data"]["session_id"]


def send(client, session_id: str, path: Path, name: str | None = None) -> dict:
    files = {"file": (name or path.name, path.read_bytes(), "application/octet-stream")}
    response = client.post(f"/api/imports/{session_id}/files", files=files)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def finish(client, session_id: str) -> dict:
    response = client.post(f"/api/imports/{session_id}/finish")
    assert response.status_code == 200, response.text
    return response.json()["data"]


def comparable(data: dict) -> list[dict]:
    keys = ("link_reasons", "summary", "match", "candidates", "suggested_action", "warnings")
    return [
        {
            "names": [a["original_name"] for a in group["attachments"]],
            "kinds": [a["kind"] for a in group["attachments"]],
            **{key: group[key] for key in keys},
        }
        for group in data["groups"]
    ]


def test_files_then_finish_groups_invoice_and_order(client, tmp_path, fake_recognition):
    order_png = png(tmp_path / "uploads", "办公-转接头-交易订单.png")
    fake_recognition.set(order_png.name, jd_order(), category="办公")
    session_id = start(client)

    invoice = send(client, session_id, jd_invoice(tmp_path))
    order = send(client, session_id, order_png)

    assert invoice["status"] == "imported" and invoice["attachment"]["kind"] == "invoice"
    assert invoice["recognized_as"].startswith("发票")
    assert invoice["message"] == "" and invoice["existing_expense_id"] is None
    assert order["recognized_as"] == "订单明细（电商订单）"
    assert order["attachment"]["evidence"]["order_no"] == "3386 0000 0001"
    data = finish(client, session_id)
    assert data["session_id"] == session_id
    assert len(data["groups"]) == 1 and data["groups"][0]["link_reasons"] == ["订单号一致"]
    assert (data["duplicates"], data["errors"], data["notices"]) == ([], [], [])

    result = confirm(client, data, payload(data["groups"][0]))

    assert len(result["created"]) == 1
    assert client.post(f"/api/imports/{session_id}/finish").status_code == 404


def test_finish_equals_batch_import_on_fresh_app(app_factory, tmp_path, fake_recognition):
    order_png = png(tmp_path / "uploads", "办公-转接头-交易订单.png")
    fake_recognition.set(order_png.name, jd_order(), category="办公")
    bank_png = png(tmp_path / "uploads", "随手截图.png")
    paths = (jd_invoice(tmp_path), order_png, bank_png)

    with app_factory("batch") as batch_client:
        batch = upload(batch_client, *paths)
    with app_factory("stepwise") as step_client:
        session_id = start(step_client)
        for path in paths:
            send(step_client, session_id, path)
        stepwise = finish(step_client, session_id)
        again = finish(step_client, session_id)

    assert comparable(stepwise) == comparable(batch)
    assert comparable(again) == comparable(stepwise)


@pytest.fixture
def app_factory(tmp_path):
    from contextlib import contextmanager

    from fastapi.testclient import TestClient

    from invoice_sorting.config import Settings
    from invoice_sorting.main import create_app

    @contextmanager
    def make(name: str):
        settings = Settings(
            data_dir=tmp_path / name,
            open_browser=False,
            watch_inbox=False,
            frontend_dist=tmp_path / "no-frontend",
        )
        with TestClient(create_app(settings)) as test_client:
            yield test_client

    return make


def test_duplicate_file_and_duplicate_invoice_no(client, tmp_path, fake_recognition):
    session_id = start(client)
    invoice_pdf = jd_invoice(tmp_path)
    first = send(client, session_id, invoice_pdf)

    same_file = send(client, session_id, invoice_pdf, "再次.pdf")
    renamed = tmp_path / "uploads" / "copy.pdf"
    shutil.copyfile(FIXTURES_DIR / "invoices" / "jd_spaced_labels.pdf", renamed)
    with renamed.open("ab") as handle:
        handle.write(b"\n% trailing bytes change sha256\n")
    same_invoice = send(client, session_id, renamed)

    assert first["status"] == "imported"
    assert same_file == {
        "original_name": "再次.pdf",
        "status": "duplicate",
        "attachment": None,
        "recognized_as": "未识别",
        "message": "文件已导入",
        "existing_expense_id": None,
    }
    assert same_invoice["status"] == "duplicate"
    assert same_invoice["message"].startswith("发票号码") and same_invoice["attachment"] is None
    data = finish(client, session_id)
    assert [d["original_name"] for d in data["duplicates"]] == ["再次.pdf", "copy.pdf"]
    assert len(data["groups"]) == 1


def test_error_results_for_unsupported_and_empty_files(client, tmp_path):
    session_id = start(client)
    text = tmp_path / "说明.txt"
    text.write_text("hello", encoding="utf-8")
    empty = tmp_path / "空.pdf"
    empty.write_bytes(b"")

    unsupported = send(client, session_id, text)
    blank = send(client, session_id, empty)

    for result in (unsupported, blank):
        assert result["status"] == "error" and result["attachment"] is None
        assert result["message"] and result["recognized_as"] == "未识别"
    data = finish(client, session_id)
    assert [e["original_name"] for e in data["errors"]] == ["说明.txt", "空.pdf"]
    assert data["groups"] == []


def test_oversized_upload_is_error_result(client, tmp_path, monkeypatch):
    monkeypatch.setattr("invoice_sorting.attachments.uploads.MAX_UPLOAD_BYTES", 10)
    session_id = start(client)

    result = send(client, session_id, png(tmp_path, "big.png"))

    assert result["status"] == "error" and "上限" in result["message"]


def test_unrecognized_invoice_by_filename_is_notice(client, tmp_path, fake_recognition):
    session_id = start(client)
    pdf = blank_pdf(tmp_path / "uploads", "发票.pdf")
    fake_recognition.set(pdf.name, recognized("unknown", recognizer="filename"))

    result = send(client, session_id, pdf)

    assert result["status"] == "imported"
    assert result["message"] == importer_service.UNRECOGNIZED_INVOICE_HINT
    assert result["recognized_as"] == "发票（按文件名判断）"
    assert finish(client, session_id)["notices"][0]["original_name"] == pdf.name


def test_unknown_session_returns_404(client, tmp_path):
    response = client.post("/api/imports/nope/finish")
    assert response.status_code == 404 and response.json()["error"] == EXPIRED
    files = {"file": ("a.png", png(tmp_path, "a.png").read_bytes(), "image/png")}
    response = client.post("/api/imports/nope/files", files=files)
    assert response.status_code == 404 and response.json()["error"] == EXPIRED


def test_finish_skips_deleted_or_assigned_attachments(client, tmp_path, fake_recognition):
    session_id = start(client)
    first = send(client, session_id, png(tmp_path, "a.png"))
    second = send(client, session_id, png(tmp_path, "b.png"))
    client.delete(f"/api/attachments/{first['attachment']['id']}")

    data = finish(client, session_id)

    assert [g["attachments"][0]["id"] for g in data["groups"]] == [second["attachment"]["id"]]


@pytest.fixture
def rail_invoice(monkeypatch):
    parsed = parsed_invoice(
        invoice_no="26312000000000009900",
        issued_on=date(2026, 9, 10),
        total_cents=55300,
        seller_name="中国铁路",
        item_summary="铁路客运",
        travel={"date": "2026-09-03"},
    )
    monkeypatch.setattr(
        importer_service,
        "parse_invoice_file",
        lambda path: parsed if path.suffix == ".pdf" else None,
    )


def test_finish_uses_travel_date_from_import(client, tmp_path, fake_recognition, rail_invoice):
    session_id = start(client)
    send(client, session_id, blank_pdf(tmp_path / "uploads", "火车票.pdf"))

    group = finish(client, session_id)["groups"][0]

    assert group["summary"]["spent_on"] == "2026-09-03"


def test_retry_after_error_then_finish_again(client, tmp_path, fake_recognition):
    session_id = start(client)
    bad = tmp_path / "坏.txt"
    bad.write_text("x", encoding="utf-8")
    send(client, session_id, bad)
    first = finish(client, session_id)

    send(client, session_id, png(tmp_path, "补传.png"))
    second = finish(client, session_id)

    assert first["groups"] == [] and len(first["errors"]) == 1
    assert [g["attachments"][0]["original_name"] for g in second["groups"]] == ["补传.png"]
    assert second["errors"] == first["errors"]
