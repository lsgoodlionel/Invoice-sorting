"""差旅住宿凭证：住宿组摘要、只有订单建记录、分次补传住宿发票与交通票的匹配与金额并入。"""

from datetime import date

from invoice_sorting.db.models import Category, Expense
from invoice_sorting.importer.auto_confirm import auto_confirm_entries
from invoice_sorting.importer.groups import build_groups
from invoice_sorting.importer.items import item_from_attachment
from invoice_sorting.importer.matching import find_candidates
from tests import lodging_factory as lf
from tests.conftest import FIXTURES_DIR


def entries(*attachments):
    return [(attachment, item_from_attachment(attachment)) for attachment in attachments]


def create_via_api(client, *attachments) -> dict:
    ids = [attachment.id for attachment in attachments]
    response = client.post("/api/attachments/create-expenses", json={"ids": ids})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_lodging_group_summary_sums_invoices_and_ignores_order(session, settings, tmp_path):
    attachments = (
        lf.hotel_invoice(session, settings, tmp_path),
        lf.hotel_order(session, settings, tmp_path),
        lf.train_invoice(session, settings, tmp_path),
        lf.train_invoice(session, settings, tmp_path, returning=True),
    )

    groups = build_groups(session, entries(*attachments))

    assert len(groups) == 1
    group = groups[0]
    assert group.link_reasons == ("酒店发票与订单一致", "往返酒店所在地的交通凭证")
    summary = group.summary
    assert summary.amount_cents == lf.ROOM_CENTS + lf.OUTBOUND_CENTS + lf.RETURN_CENTS
    assert summary.merchant == lf.HOTEL
    assert summary.summary == f"{lf.HOTEL} 1晚 + 交通 2 张"
    assert summary.category_id == lf.travel_category(session)
    assert summary.spent_on == lf.AUG_15 and summary.invoice_exempt is False
    assert group.suggested_action == "create"


def test_confirmed_lodging_group_has_complete_checklist(session, settings, tmp_path):
    attachments = (
        lf.hotel_invoice(session, settings, tmp_path),
        lf.hotel_order(session, settings, tmp_path),
        lf.train_invoice(session, settings, tmp_path),
        lf.train_invoice(session, settings, tmp_path, returning=True),
    )

    result = auto_confirm_entries(session, settings, entries(*attachments))

    expense = session.get(Expense, result.created[0])
    assert expense.amount_cents == 72000 and len(expense.attachments) == 4
    states = lf.checklist_states(expense)
    assert states["transport"] == ("required", "present")
    assert states["order"] == ("required", "present")
    assert "itinerary" not in states
    assert expense.status == "complete"


def test_hotel_invoice_without_order_uses_seller_and_invoice_date(session, settings, tmp_path):
    invoice = lf.hotel_invoice(session, settings, tmp_path)
    train = lf.train_invoice(session, settings, tmp_path, returning=True)

    group = build_groups(session, entries(invoice, train))[0]

    assert group.summary.merchant == lf.HOTEL_SELLER
    assert group.summary.spent_on == lf.AUG_16
    assert group.summary.summary == f"{lf.HOTEL_SELLER} + 交通 1 张"


def test_nights_from_dates_and_category_fallback_when_travel_archived(session, settings, tmp_path):
    session.get(Category, lf.travel_category(session)).archived = True
    order = lf.hotel_order(session, settings, tmp_path)
    order.evidence_data.details = {
        **order.evidence_data.details,
        "nights": "",
        "check_out": "2026-08-18",
    }
    session.flush()

    summary = build_groups(session, entries(order))[0].summary

    assert summary.summary == f"{lf.HOTEL} 3晚"
    assert summary.category_id != lf.travel_category(session)


def test_order_only_then_invoice_then_return_ticket(client, session, settings, tmp_path):
    order = lf.hotel_order(session, settings, tmp_path)
    session.commit()

    created = create_via_api(client, order)["created"]
    session.expire_all()
    expense = session.get(Expense, created[0])
    assert (expense.amount_cents, expense.merchant) == (lf.ROOM_CENTS, lf.HOTEL)
    assert expense.invoice_exempt is False and expense.spent_on == lf.AUG_15
    states = lf.checklist_states(expense)
    assert states["invoice"] == ("required", "missing")
    assert states["transport"] == ("required", "missing")

    invoice = lf.hotel_invoice(session, settings, tmp_path)
    session.commit()
    assert create_via_api(client, invoice)["attached"] == [expense.id]
    session.expire_all()
    assert expense.amount_cents == lf.ROOM_CENTS
    assert not any("并入" in note for note in lf.timeline_notes(expense))

    ticket = lf.train_invoice(session, settings, tmp_path, returning=True)
    session.commit()
    assert create_via_api(client, ticket)["attached"] == [expense.id]
    session.expire_all()
    assert expense.amount_cents == lf.ROOM_CENTS + lf.RETURN_CENTS
    assert "并入交通票 ¥120.00，金额更新为 ¥620.00" in lf.timeline_notes(expense)
    assert lf.checklist_states(expense)["transport"] == ("required", "present")
    assert expense.status == "complete"


def lodging_expense(session, settings, tmp_path, amount=lf.ROOM_CENTS):
    """已建好的住宿记录：酒店订单 + 住宿发票，金额 500。"""
    result = auto_confirm_entries(
        session,
        settings,
        entries(
            lf.hotel_order(session, settings, tmp_path),
            lf.hotel_invoice(session, settings, tmp_path),
        ),
    )
    expense = session.get(Expense, result.created[0])
    expense.amount_cents = amount
    session.flush()
    return expense


def test_return_ticket_scores_by_date_and_city(session, settings, tmp_path):
    expense = lodging_expense(session, settings, tmp_path)
    ticket = lf.train_invoice(session, settings, tmp_path, returning=True)

    match, _others = find_candidates(session, [item_from_attachment(ticket)])

    assert match is not None and match.expense is expense
    assert "往返 苏州 的交通凭证（入住 08-15、离店 08-16）" in match.reasons
    assert not any(reason.startswith("已有") for reason in match.reasons)


def test_ticket_for_other_city_or_date_is_not_merged(session, settings, tmp_path):
    lodging_expense(session, settings, tmp_path)
    beijing = lf.train_invoice(session, settings, tmp_path, **{"from": "北京南", "to": "上海虹桥"})
    late = lf.train_invoice(session, settings, tmp_path, returning=True, date="2026-08-19")

    for ticket in (beijing, late):
        match, _others = find_candidates(session, [item_from_attachment(ticket)])
        assert match is None


def test_long_stay_record_found_for_late_return_ticket(session, settings, tmp_path):
    expense = lodging_expense(session, settings, tmp_path)
    order = next(a for a in expense.attachments if a.kind == "order")
    order.evidence_data.details = {**order.evidence_data.details, "check_out": "2026-08-30"}
    session.flush()
    ticket = lf.train_invoice(session, settings, tmp_path, returning=True, date="2026-08-30")

    match, _others = find_candidates(session, [item_from_attachment(ticket)])

    assert match is not None and match.expense is expense


def test_candidates_endpoint_lists_lodging_record(client, session, settings, tmp_path):
    expense = lodging_expense(session, settings, tmp_path)
    ticket = lf.train_invoice(session, settings, tmp_path)
    session.commit()

    response = client.get(f"/api/attachments/{ticket.id}/candidates")

    assert response.status_code == 200, response.text
    first = response.json()["data"][0]
    assert first["expense_id"] == expense.id
    assert "往返 苏州 的交通凭证（入住 08-15、离店 08-16）" in first["reasons"]


def test_inbox_auto_confirm_merges_ticket_amount(session, settings, tmp_path):
    expense = lodging_expense(session, settings, tmp_path)
    ticket = lf.train_invoice(session, settings, tmp_path)

    result = auto_confirm_entries(session, settings, entries(ticket))

    assert result.attached == [expense.id]
    assert expense.amount_cents == lf.ROOM_CENTS + lf.OUTBOUND_CENTS
    assert "并入交通票 ¥100.00，金额更新为 ¥600.00" in lf.timeline_notes(expense)


def test_manual_amount_is_kept_when_ticket_attached(session, settings, tmp_path):
    expense = lodging_expense(session, settings, tmp_path, amount=48000)
    ticket = lf.train_invoice(session, settings, tmp_path)

    auto_confirm_entries(session, settings, entries(ticket))

    assert expense.amount_cents == 48000
    assert "并入交通票 ¥100.00，金额未自动调整（已手动修改过）" in lf.timeline_notes(expense)
    assert expense.spent_on == date(2026, 8, 15)


def test_import_api_exposes_hotel_order_details(client):
    fixture = FIXTURES_DIR / "evidence" / "ctrip_hotel.pdf"
    files = [("files", (fixture.name, fixture.read_bytes(), "application/pdf"))]

    response = client.post("/api/imports", files=files)

    assert response.status_code == 200, response.text
    attachment = response.json()["data"]["groups"][0]["attachments"][0]
    details = attachment["evidence"]["details"]
    assert attachment["evidence"]["recognizer"] == "hotel_booking"
    assert details["check_in"] and details["check_out"] and details["city"]
