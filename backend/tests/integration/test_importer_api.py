"""导入 API：拖入发票建记录、重复判定、匹配已支出、损坏文件、购方校验（T01/T02/T03/T17/T19）。"""

import io
import shutil
from pathlib import Path

from PIL import Image
from sqlalchemy import func, select

from invoice_sorting.db.models import Category, Expense, MerchantMemory
from tests.conftest import FIXTURES_DIR

INVOICES = FIXTURES_DIR / "invoices"
SAME_LINE_NO = "26312000000123456789"
MULTILINE_NO = "26312000000987654321"


def sample(tmp_path: Path, name: str, as_name: str | None = None) -> Path:
    target = tmp_path / "uploads" / (as_name or name)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(INVOICES / name, target)
    return target


def upload(client, *paths: Path) -> dict:
    files = [
        ("files", (path.name, path.read_bytes(), "application/octet-stream")) for path in paths
    ]
    return client.post("/api/imports", files=files).json()


def confirm(client, session_id: str, *rows: dict):
    return client.post(f"/api/imports/{session_id}/confirm", json={"rows": list(rows)})


def row_payload(row: dict, action: str = "create", **overrides) -> dict:
    suggested = row["suggested"]
    payload = {
        "row_id": row["row_id"],
        "action": action,
        "spent_on": suggested["spent_on"],
        "amount_cents": suggested["amount_cents"],
        "merchant": suggested["merchant"],
        "summary": suggested["summary"],
        "category_id": suggested["category_id"],
    }
    payload.update(overrides)
    return payload


def category_id(session, name: str) -> int:
    return session.scalar(select(Category.id).where(Category.name == name))


def expense_count(session) -> int:
    return session.scalar(select(func.count(Expense.id)))


def test_t01_import_digital_invoice_and_create(client, session, settings, tmp_path):
    data = upload(client, sample(tmp_path, "digital_same_line.pdf"))["data"]

    assert data["duplicates"] == [] and data["errors"] == [] and data["attachments"] == []
    row = data["rows"][0]
    assert row["is_invoice"] is True and row["match"] is None and row["warnings"] == []
    assert row["suggested"] == {
        "spent_on": "2026-09-15",
        "amount_cents": 96000,
        "merchant": "上海示例科技有限公司",
        "summary": "鼠标",
        "category_id": category_id(session, "易耗品"),
        "is_online": False,
    }
    attachment = row["attachment"]
    assert attachment["kind"] == "invoice" and attachment["expense_id"] is None
    assert attachment["file_name"] == f"发票_{SAME_LINE_NO}.pdf"
    assert attachment["invoice"]["confirmed"] is False

    result = confirm(client, data["session_id"], row_payload(row)).json()["data"]

    assert result["attached"] == [] and result["skipped"] == 0
    detail = client.get(f"/api/expenses/{result['created'][0]}").json()["data"]
    assert detail["status"] == "invoiced"
    assert detail["amount_cents"] == 96000 and detail["merchant"] == "上海示例科技有限公司"
    assert detail["folder_path"].startswith("2026/09/")
    assert detail["attachments"][0]["invoice"]["confirmed"] is True
    stored = settings.library_dir / detail["folder_path"] / f"发票_{SAME_LINE_NO}.pdf"
    assert stored.is_file()
    assert detail["timeline"][-1]["note"] == "导入发票"
    assert session.get(MerchantMemory, "上海示例科技有限公司") is not None


def test_confirm_removes_processed_rows_from_session(client, tmp_path):
    data = upload(client, sample(tmp_path, "digital_same_line.pdf"))["data"]
    row = data["rows"][0]
    assert confirm(client, data["session_id"], row_payload(row)).status_code == 200

    response = confirm(client, data["session_id"], row_payload(row))

    assert response.status_code == 404
    assert response.json()["error"] == "导入会话已过期，请重新导入"


def test_t02_same_file_imported_twice(client, session, tmp_path):
    path = sample(tmp_path, "digital_same_line.pdf")
    first = upload(client, path)["data"]
    created = confirm(client, first["session_id"], row_payload(first["rows"][0])).json()["data"]

    second = upload(client, path)["data"]

    assert second["rows"] == []
    assert second["duplicates"] == [
        {
            "original_name": "digital_same_line.pdf",
            "existing_expense_id": created["created"][0],
            "reason": "文件已导入",
        }
    ]
    assert expense_count(session) == 1


def test_t02_same_invoice_number_different_files(client, settings, tmp_path):
    pdf = sample(tmp_path, "digital_multiline.pdf")
    ofd = sample(tmp_path, "digital_text_only.ofd")

    data = upload(client, pdf, ofd)["data"]

    assert len(data["rows"]) == 1
    duplicate = data["duplicates"][0]
    assert duplicate["original_name"] == "digital_text_only.ofd"
    assert duplicate["reason"] == f"发票号码 {MULTILINE_NO} 已存在"
    assert duplicate["existing_expense_id"] is None
    unassigned = client.get("/api/attachments/unassigned").json()["data"]
    assert len(unassigned) == 1
    assert len(list((settings.library_dir / "待归属").iterdir())) == 1

    created = confirm(client, data["session_id"], row_payload(data["rows"][0])).json()["data"]
    again = upload(client, sample(tmp_path, "digital_text_only.ofd", "副本.ofd"))["data"]
    assert again["duplicates"][0]["existing_expense_id"] == created["created"][0]


def test_t03_match_spent_expense_and_attach(client, session, tmp_path):
    spent = client.post(
        "/api/expenses", json={"spent_on": "2026-09-12", "amount_cents": 96000, "merchant": "京东"}
    ).json()["data"]
    data = upload(client, sample(tmp_path, "digital_same_line.pdf"))["data"]
    row = data["rows"][0]
    assert row["match"] == {
        "expense_id": spent["id"],
        "merchant": "京东",
        "amount_cents": 96000,
        "spent_on": "2026-09-12",
    }

    payload = row_payload(row, "attach", expense_id=spent["id"], amount_cents=1, merchant="改")
    result = confirm(client, data["session_id"], payload).json()["data"]

    assert result == {"created": [], "attached": [spent["id"]], "skipped": 0}
    detail = client.get(f"/api/expenses/{spent['id']}").json()["data"]
    assert detail["status"] == "invoiced"
    assert detail["amount_cents"] == 96000 and detail["spent_on"] == "2026-09-12"
    assert detail["merchant"] == "京东"
    assert detail["category_id"] == category_id(session, "易耗品")
    assert expense_count(session) == 1


def test_attach_keeps_existing_category(client, session, tmp_path):
    office = category_id(session, "办公用品")
    spent = client.post(
        "/api/expenses",
        json={
            "spent_on": "2026-09-15",
            "amount_cents": 96000,
            "merchant": "京东",
            "category_id": office,
        },
    ).json()["data"]
    data = upload(client, sample(tmp_path, "digital_same_line.pdf"))["data"]

    payload = row_payload(data["rows"][0], "attach", expense_id=spent["id"])
    assert confirm(client, data["session_id"], payload).status_code == 200

    assert client.get(f"/api/expenses/{spent['id']}").json()["data"]["category_id"] == office


def test_t17_corrupt_encrypted_and_image_files(client, tmp_path):
    image = tmp_path / "uploads" / "截图.png"
    image.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (20, 20), "blue").save(image)
    paths = [
        sample(tmp_path, "corrupt.pdf"),
        sample(tmp_path, "encrypted.pdf"),
        sample(tmp_path, "not_invoice.pdf"),
        sample(tmp_path, "corrupt.pdf", "发票_损坏.pdf"),
        image,
    ]
    paths[3].write_bytes(paths[3].read_bytes() + b"\n%extra")

    response = client.post(
        "/api/imports",
        files=[("files", (p.name, p.read_bytes(), "application/pdf")) for p in paths],
    )

    data = response.json()["data"]
    assert response.status_code == 200
    assert data["rows"] == []
    assert len(data["attachments"]) == 5
    # 文件名含“发票/invoice”但解析失败 → 作为附件导入并提示
    hint = "无法识别发票内容，已作为附件导入"
    assert data["notices"] == [
        {"original_name": "not_invoice.pdf", "message": hint},
        {"original_name": "发票_损坏.pdf", "message": hint},
    ]
    assert data["errors"] == []


def test_unsupported_and_empty_files_do_not_block_others(client, tmp_path):
    files = [
        ("files", ("说明.txt", b"hello", "text/plain")),
        ("files", ("空.pdf", b"", "application/pdf")),
        ("files", ("digital_same_line.pdf", (INVOICES / "digital_same_line.pdf").read_bytes())),
    ]

    data = client.post("/api/imports", files=files).json()["data"]

    assert len(data["rows"]) == 1
    names = [item["original_name"] for item in data["errors"]]
    assert names == ["说明.txt", "空.pdf"]
    assert "不支持的文件类型" in data["errors"][0]["error"]


def test_t19_buyer_mismatch_and_parser_warnings(client, tmp_path):
    client.put("/api/settings", json={"buyer_name": "某某大学", "buyer_tax_id": ""})

    data = upload(client, sample(tmp_path, "digital_upper_mismatch.pdf"))["data"]

    row = data["rows"][0]
    assert "大小写金额不一致" in row["warnings"]
    assert "购方名称或税号与设置不一致，请核对发票抬头" in row["warnings"]
    assert row["attachment"]["invoice"]["buyer_mismatch"] is True


def test_rail_ticket_uses_travel_date(client, session, tmp_path):
    data = upload(client, sample(tmp_path, "rail_ticket.pdf"))["data"]

    suggested = data["rows"][0]["suggested"]
    assert suggested["spent_on"] == "2026-09-12"
    assert suggested["category_id"] == category_id(session, "差旅交通")


def test_skip_keeps_invoice_unassigned(client, tmp_path):
    data = upload(client, sample(tmp_path, "digital_same_line.pdf"))["data"]

    result = confirm(
        client, data["session_id"], {"row_id": data["rows"][0]["row_id"], "action": "skip"}
    )

    assert result.json()["data"] == {"created": [], "attached": [], "skipped": 1}
    unassigned = client.get("/api/attachments/unassigned").json()["data"]
    assert unassigned[0]["invoice"]["confirmed"] is False


def test_failed_row_rolls_back_everything(client, session, settings, tmp_path):
    data = upload(
        client, sample(tmp_path, "digital_same_line.pdf"), sample(tmp_path, "rail_ticket.pdf")
    )["data"]
    first, second = data["rows"]
    before = settings.data_dir / "文件库" / "待归属" / first["attachment"]["file_name"]
    assert before.is_file()

    response = confirm(
        client,
        data["session_id"],
        row_payload(first),
        row_payload(second, "attach", expense_id=999),
    )

    assert response.status_code == 404
    assert response.json()["error"] == "文件“rail_ticket.pdf”：支出记录不存在"
    session.expire_all()
    assert expense_count(session) == 0
    assert before.is_file()
    assert not any((settings.library_dir / "2026").rglob("*.pdf"))
    ok = confirm(client, data["session_id"], row_payload(first), row_payload(second))
    assert ok.status_code == 200 and len(ok.json()["data"]["created"]) == 2


def test_rollback_restores_renamed_attach_target(client, session, settings, tmp_path):
    spent = client.post(
        "/api/expenses", json={"spent_on": "2026-09-15", "amount_cents": 96000, "merchant": "京东"}
    ).json()["data"]
    data = upload(
        client, sample(tmp_path, "digital_same_line.pdf"), sample(tmp_path, "rail_ticket.pdf")
    )["data"]
    first, second = data["rows"]

    response = confirm(
        client,
        data["session_id"],
        row_payload(first, "attach", expense_id=spent["id"]),
        row_payload(second, amount_cents=None),
    )

    assert response.status_code == 400
    assert response.json()["error"] == "文件“rail_ticket.pdf”：请填写金额"
    folder = settings.library_dir / spent["folder_path"]
    assert folder.is_dir() and not any(folder.iterdir())
    pending = settings.library_dir / "待归属" / first["attachment"]["file_name"]
    assert pending.is_file()


def test_confirm_validation_errors(client, tmp_path):
    data = upload(client, sample(tmp_path, "digital_same_line.pdf"))["data"]
    row = data["rows"][0]
    session_id = data["session_id"]

    attach = confirm(client, session_id, row_payload(row, "attach"))
    unknown = confirm(client, session_id, {"row_id": "nope", "action": "skip"})
    merchant = confirm(client, session_id, row_payload(row, merchant="  "))
    no_date = confirm(client, session_id, row_payload(row, spent_on=None))
    twice = confirm(client, session_id, row_payload(row), row_payload(row))

    assert attach.json()["error"] == "文件“digital_same_line.pdf”：挂到已有记录时需要选择记录"
    assert unknown.json()["error"] == "导入行不存在或已处理：nope"
    assert merchant.json()["error"] == "文件“digital_same_line.pdf”：请填写商家"
    assert no_date.json()["error"] == "文件“digital_same_line.pdf”：请填写支出日期"
    assert twice.json()["error"] == "文件“digital_same_line.pdf”：同一行不能重复提交"


def test_confirm_rejects_attachment_already_assigned(client, tmp_path):
    spent = client.post(
        "/api/expenses", json={"spent_on": "2026-01-01", "amount_cents": 1, "merchant": "甲"}
    ).json()["data"]
    data = upload(client, sample(tmp_path, "digital_same_line.pdf"))["data"]
    row = data["rows"][0]
    client.patch(f"/api/attachments/{row['attachment']['id']}", json={"expense_id": spent["id"]})

    response = confirm(client, data["session_id"], row_payload(row))

    assert response.json()["error"] == (
        f"文件“digital_same_line.pdf”：已归属到记录 #{spent['id']}，请刷新后重试"
    )


def test_confirm_unknown_session(client):
    response = confirm(client, "missing", {"row_id": "x", "action": "skip"})

    assert response.status_code == 404
    assert response.json()["error"] == "导入会话已过期，请重新导入"


def test_import_requires_files(client):
    response = client.post("/api/imports", files=[])

    assert response.status_code == 422


def test_import_response_attachment_is_downloadable(client, tmp_path):
    data = upload(client, sample(tmp_path, "digital_same_line.pdf"))["data"]

    content = client.get(data["rows"][0]["attachment"]["url"]).content

    assert io.BytesIO(content).read(4) == b"%PDF"
