"""差旅住宿凭证：各挂接路径的金额并入、往来交通凭证清单项、多发票组确认与规则 v6 升级。"""

from datetime import date

import pytest
from sqlalchemy import select

from invoice_sorting.attachments import recognition
from invoice_sorting.attachments.evidence_records import kind_for_evidence
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.common.errors import AppError
from invoice_sorting.db.models import AppSetting, ChecklistRule, Expense
from invoice_sorting.db.seed import LODGING_KEYWORDS, RULES_VERSION, sync_default_rules
from invoice_sorting.evidence import RecognizedEvidence
from invoice_sorting.expenses.amounts import invoice_total, merge_invoice_amounts
from invoice_sorting.expenses.service import create_expense, refresh_expense
from invoice_sorting.importer.confirm import confirm_groups
from invoice_sorting.importer.group_summary import category_from_filenames
from invoice_sorting.importer.schemas import ConfirmGroup
from tests import lodging_factory as lf
from tests.evidence_factory import item
from tests.invoice_factory import blank_pdf, parsed_invoice, store_invoice

MERGED = "并入交通票 ¥100.00，金额更新为 ¥600.00"


def lodging_expense(session, settings, tmp_path, amount=lf.ROOM_CENTS) -> Expense:
    expense = create_expense(
        session,
        settings,
        spent_on=lf.AUG_15,
        amount_cents=amount,
        merchant=lf.HOTEL,
        category_id=lf.travel_category(session),
    )
    lf.hotel_order(session, settings, tmp_path, expense=expense)
    lf.hotel_invoice(session, settings, tmp_path, expense=expense)
    return refresh_expense(session, settings, expense)


def reload(session, expense_id: int) -> Expense:
    session.expire_all()
    return session.get(Expense, expense_id)


def test_bulk_assign_merges_ticket_amount(client, session, settings, tmp_path):
    expense = lodging_expense(session, settings, tmp_path)
    ticket = lf.train_invoice(session, settings, tmp_path)
    session.commit()

    response = client.post(
        "/api/attachments/bulk-assign", json={"ids": [ticket.id], "expense_id": expense.id}
    )

    assert response.status_code == 200, response.text
    expense = reload(session, expense.id)
    assert expense.amount_cents == lf.ROOM_CENTS + lf.OUTBOUND_CENTS
    assert MERGED in lf.timeline_notes(expense)
    assert lf.checklist_states(expense)["transport"] == ("required", "present")


def test_bulk_assign_keeps_manual_amount(client, session, settings, tmp_path):
    expense = lodging_expense(session, settings, tmp_path, amount=48000)
    ticket = lf.train_invoice(session, settings, tmp_path)
    session.commit()

    client.post("/api/attachments/bulk-assign", json={"ids": [ticket.id], "expense_id": expense.id})

    expense = reload(session, expense.id)
    assert expense.amount_cents == 48000
    assert "并入交通票 ¥100.00，金额未自动调整（已手动修改过）" in lf.timeline_notes(expense)


def test_patch_attachment_expense_merges_amount(client, session, settings, tmp_path):
    expense = lodging_expense(session, settings, tmp_path)
    ticket = lf.train_invoice(session, settings, tmp_path)
    session.commit()

    response = client.patch(f"/api/attachments/{ticket.id}", json={"expense_id": expense.id})

    assert response.status_code == 200, response.text
    assert reload(session, expense.id).amount_cents == lf.ROOM_CENTS + lf.OUTBOUND_CENTS


def test_upload_to_expense_merges_recognized_ticket(
    client, session, settings, tmp_path, monkeypatch
):
    expense = lodging_expense(session, settings, tmp_path)
    session.commit()
    travel = {"date": "2026-08-16", "from": "苏州园区", "to": "上海虹桥", "train_or_flight": "G7"}
    ticket = parsed_invoice(
        invoice_no="26329100000000009999",
        issued_on=date(2026, 8, 20),
        total_cents=lf.RETURN_CENTS,
        seller_name="中国铁路上海局集团有限公司",
        item_summary="苏州园区-上海虹桥 G7",
        tax_category="",
        parser="rail_ticket",
        travel=travel,
    )
    monkeypatch.setattr(recognition, "parse_invoice_file", lambda _path: ticket)
    pdf = blank_pdf(tmp_path / "uploads", "返程.pdf")

    response = client.post(
        f"/api/expenses/{expense.id}/attachments",
        files=[("files", (pdf.name, pdf.read_bytes(), "application/pdf"))],
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["amount_cents"] == lf.ROOM_CENTS + lf.RETURN_CENTS
    assert any("金额更新为 ¥620.00" in event["note"] for event in data["timeline"])


def test_non_invoice_or_first_invoice_does_not_touch_amount(session, settings, tmp_path):
    expense = create_expense(
        session, settings, spent_on=lf.AUG_15, amount_cents=30000, merchant=lf.HOTEL
    )
    events = len(expense.status_events)

    lf.hotel_invoice(session, settings, tmp_path, expense=expense)

    assert merge_invoice_amounts(session, expense, 0) is False
    assert invoice_total(session, expense) == lf.ROOM_CENTS
    assert expense.amount_cents == 30000 and len(expense.status_events) == events


def test_second_ordinary_invoice_is_labelled_invoice(session, settings, tmp_path):
    expense = create_expense(
        session, settings, spent_on=lf.AUG_15, amount_cents=1000, merchant="文具店"
    )
    store_invoice(
        session,
        settings,
        tmp_path,
        expense=expense,
        invoice={"invoice_no": "1", "total_cents": 1000, "confirmed": True},
    )
    previous = invoice_total(session, expense)
    store_invoice(
        session,
        settings,
        tmp_path,
        expense=expense,
        invoice={"invoice_no": "2", "total_cents": 500, "confirmed": True},
    )

    assert merge_invoice_amounts(session, expense, previous) is True
    assert expense.amount_cents == 1500
    assert "并入发票 ¥5.00，金额更新为 ¥15.00" in lf.timeline_notes(expense)


def test_transport_item_satisfied_by_transport_attachment(session, settings, tmp_path):
    expense = lodging_expense(session, settings, tmp_path)
    assert lf.checklist_states(expense)["transport"] == ("required", "missing")
    assert "往返酒店所在地" in next(
        item.hint for item in expense.checklist_items if item.attachment_kind == "transport"
    )

    lf.evidence(session, settings, tmp_path, "12306.png", AttachmentKind.TRANSPORT, expense)
    refresh_expense(session, settings, expense)

    assert lf.checklist_states(expense)["transport"] == ("required", "present")
    assert expense.status == "complete"


def test_old_invoice_without_details_does_not_count_as_transport(session, settings, tmp_path):
    expense = lodging_expense(session, settings, tmp_path)
    ticket = lf.train_invoice(session, settings, tmp_path, expense=expense)
    ticket.invoice_data.details = None
    refresh_expense(session, settings, expense)

    assert lf.checklist_states(expense)["transport"] == ("required", "missing")


def confirm_group(session, settings, attachments, **fields):
    group = ConfirmGroup(
        group_id="g",
        attachment_ids=[attachment.id for attachment in attachments],
        action="create",
        spent_on=lf.AUG_15,
        amount_cents=72000,
        merchant=lf.HOTEL,
        category_id=lf.travel_category(session),
        **fields,
    )
    return confirm_groups(session, settings, None, [group])


def test_confirm_accepts_lodging_invoice_with_ticket_invoices(session, settings, tmp_path):
    attachments = [
        lf.hotel_invoice(session, settings, tmp_path),
        lf.train_invoice(session, settings, tmp_path),
        lf.train_invoice(session, settings, tmp_path, returning=True),
    ]

    result = confirm_group(session, settings, attachments)

    expense = session.get(Expense, result.created[0])
    assert expense.amount_cents == 72000 and len(expense.attachments) == 3
    assert expense.status == "invoiced"  # 缺酒店订单


def test_confirm_rejects_two_lodging_invoices(session, settings, tmp_path):
    attachments = [
        lf.hotel_invoice(session, settings, tmp_path),
        lf.hotel_invoice(session, settings, tmp_path),
    ]

    with pytest.raises(AppError, match="每组最多一张发票"):
        confirm_group(session, settings, attachments)


@pytest.mark.parametrize(
    ("recognized", "kind"),
    [
        (RecognizedEvidence("itinerary", "transport_booking"), "transport"),
        (RecognizedEvidence("order", "test", details={"vehicle": "flight"}), "transport"),
        (RecognizedEvidence("itinerary", "didi_itinerary"), "itinerary"),
    ],
)
def test_transport_evidence_kind(recognized, kind):
    assert kind_for_evidence(recognized, "x.png", AttachmentKind.OTHER) == kind


@pytest.mark.parametrize("word", ["出差", "住宿", "酒店"])
def test_travel_filename_words_map_to_travel_category(session, fake_recognition, word):
    fake_recognition.set("a.png", RecognizedEvidence("unknown", "filename"), category=word)

    found = category_from_filenames(session, (item(1, "order", original_name="a.png"),))

    assert found == lf.travel_category(session)


def test_rules_v6_upgrade_is_idempotent(session):
    travel = lf.travel_category(session)
    query = select(ChecklistRule).where(
        ChecklistRule.category_id == travel, ChecklistRule.attachment_kind == "transport"
    )
    for rule in session.scalars(query):
        session.delete(rule)
    session.merge(AppSetting(key="rules_version", value="5"))
    session.commit()

    sync_default_rules(session)
    sync_default_rules(session)

    rules = session.scalars(query).all()
    assert len(rules) == 1
    assert rules[0].level == "required"
    assert rules[0].condition == {"content_keywords": list(LODGING_KEYWORDS)}
    assert session.get(AppSetting, "rules_version").value == str(RULES_VERSION) == "6"
