from pathlib import Path

from reportlab.pdfgen import canvas


def write_apple_thread(path: Path) -> None:
    pages = [
        [
            "Gmail - Your purchases from Apple",
            "Receipt",
            "DATE",
            "October 1, 2026",
            "ORDER ID",
            "MTEST00001",
            "DOCUMENT NO.",
            "600000000001",
            "Apple Account",
            "BILLED TO PayPal",
            "App Store",
            "Demo One",
            "Monthly",
            "In-App Purchase",
            "$10.00",
            "TOTAL $10.00",
        ],
        ["Receipt", "DATE", "October 2, 2026", "Apple Account", "BILLED TO PayPal"],
        [
            "ORDER ID",
            "MTEST00002",
            "DOCUMENT NO.",
            "600000000002",
            "App Store",
            "Demo Two",
            "Credits",
            "In-App Purchase",
            "$20.00",
            "TOTAL $20.00",
        ],
        [
            "Receipt",
            "DATE",
            "October 3, 2026",
            "ORDER ID: MTEST00003",
            "DOCUMENT NO. 600000000003",
            "Apple Account",
            "BILLED TO PayPal",
            "App Store",
            "Demo Three",
            "Annual",
            "In-App Purchase",
            "$30.00",
            "TOTAL $30.00",
        ],
    ]
    pdf = canvas.Canvas(str(path))
    for lines in pages:
        text = pdf.beginText(40, 800)
        for line in lines:
            text.textLine(line)
        pdf.drawText(text)
        pdf.showPage()
    pdf.save()


def start(client) -> str:
    return client.post("/api/imports/start").json()["data"]["session_id"]


def send(client, session_id: str, path: Path) -> dict:
    response = client.post(
        f"/api/imports/{session_id}/files",
        files={"file": (path.name, path.read_bytes(), "application/pdf")},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def finish(client, session_id: str) -> dict:
    response = client.post(f"/api/imports/{session_id}/finish")
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_imports_each_apple_receipt_with_shared_source_and_rejects_duplicate(client, tmp_path):
    source = tmp_path / "Gmail - Your purchases from Apple.pdf"
    write_apple_thread(source)
    session_id = start(client)

    uploaded = send(client, session_id, source)

    assert uploaded["status"] == "imported"
    assert uploaded["message"] == "已拆分 3 张 Apple 回执"
    data = finish(client, session_id)
    assert len(data["groups"]) == 3
    attachments = [group["attachments"][0] for group in data["groups"]]
    assert {item["evidence"]["order_no"] for item in attachments} == {
        "MTEST00001",
        "MTEST00002",
        "MTEST00003",
    }
    assert {item["source"]["id"] for item in attachments} == {
        attachments[0]["source"]["id"]
    }
    assert sorted(
        (item["source"]["page_start"], item["source"]["page_end"])
        for item in attachments
    ) == [(1, 1), (2, 3), (4, 4)]
    assert all(group["summary"]["currency"] == "USD" for group in data["groups"])
    assert all(group["summary"]["is_online"] is True for group in data["groups"])
    assert all(group["summary"]["invoice_exempt"] is True for group in data["groups"])

    groups = []
    for group in data["groups"]:
        summary = group["summary"]
        groups.append(
            {
                "group_id": group["group_id"],
                "attachment_ids": [item["id"] for item in group["attachments"]],
                "action": "create",
                "spent_on": summary["spent_on"],
                "amount_cents": summary["original_amount_cents"] * 7,
                "currency": summary["currency"],
                "original_amount_cents": summary["original_amount_cents"],
                "merchant": summary["merchant"],
                "summary": summary["summary"],
                "is_online": summary["is_online"],
                "invoice_exempt": summary["invoice_exempt"],
            }
        )
    confirmed = client.post(
        f"/api/imports/{session_id}/confirm", json={"groups": groups}
    ).json()["data"]
    assert len(confirmed["created"]) == 3
    for expense_id in confirmed["created"]:
        detail = client.get(f"/api/expenses/{expense_id}").json()["data"]
        assert detail["attachment_count"] == 1
        assert detail["invoice_exempt"] is True
        assert detail["is_online"] is True
        assert isinstance(detail["checklist"], list)

    duplicate = send(client, start(client), source)
    assert duplicate["status"] == "duplicate"
    assert duplicate["message"] == "来源文件已导入"
