"""历史住宿日期迁移：原文、已有字段和幂等性。"""

from datetime import date

from fastapi.testclient import TestClient

from invoice_sorting.db.models import AppSetting, Attachment, EvidenceData, Expense, InvoiceData
from invoice_sorting.importer.items import item_from_attachment
from invoice_sorting.importer.lodging_backfill import backfill_lodging_dates
from invoice_sorting.importer.lodging_summary import lodging_night_dates
from invoice_sorting.main import create_app
from invoice_sorting.tenancy.bootstrap import open_business_db


def _expense(session, day: date) -> Expense:
    session.delete(session.get(AppSetting, "lodging_dates_backfill_version"))
    session.flush()
    expense = Expense(spent_on=day, amount_cents=20000, merchant="测试酒店")
    session.add(expense)
    session.flush()
    return expense


def _attachment(session, expense: Expense, number: int, kind: str) -> Attachment:
    attachment = Attachment(
        expense_id=expense.id,
        kind=kind,
        file_path=f"test/{number}.pdf",
        original_name=f"{number}.pdf",
        sha256=f"{number:064x}",
    )
    session.add(attachment)
    session.flush()
    return attachment


def test_backfills_old_order_and_invoice_without_using_issue_date(session):
    expense = _expense(session, date(2026, 11, 9))
    order = _attachment(session, expense, 1, "order")
    order.evidence_data = EvidenceData(
        attachment_id=order.id,
        doc_type="order",
        recognizer="hotel_booking",
        occurred_on=date(2026, 11, 3),
        raw_text="北京全季酒店\n入住日期 2026年11月1日\n离店日期 2026年11月3日\n共2晚",
        details={"hotel": "北京全季酒店", "city": "北京"},
    )
    invoice = _attachment(session, expense, 2, "invoice")
    invoice.invoice_data = InvoiceData(
        attachment_id=invoice.id,
        issued_on=date(2026, 11, 9),
        item_summary="住宿费",
        tax_category="住宿服务",
        raw_text="开票日期 2026年11月9日\n住宿日期 2026年11月1日\n离店 2026年11月3日",
    )
    session.commit()

    assert backfill_lodging_dates(session) == 2
    assert order.evidence_data.details["check_in"] == "2026-11-01"
    assert order.evidence_data.details["check_out"] == "2026-11-03"
    assert order.evidence_data.details["nights"] == "2"
    assert order.evidence_data.occurred_on == date(2026, 11, 1)
    assert invoice.invoice_data.details["check_in"] == "2026-11-01"
    assert invoice.invoice_data.issued_on == date(2026, 11, 9)
    assert lodging_night_dates([item_from_attachment(order), item_from_attachment(invoice)]) == {
        date(2026, 11, 1), date(2026, 11, 2)
    }
    assert backfill_lodging_dates(session) == 0


def test_existing_dates_and_unrelated_payment_remain_unchanged(session):
    expense = _expense(session, date(2026, 11, 1))
    order = _attachment(session, expense, 3, "order")
    order.evidence_data = EvidenceData(
        attachment_id=order.id,
        doc_type="order",
        recognizer="hotel_booking",
        occurred_on=date(2026, 11, 8),
        raw_text="入住日期 2026年11月1日\n离店日期 2026年11月3日",
        details={"check_in": "2026-11-02", "check_out": "2026-11-04"},
    )
    payment = _attachment(session, expense, 4, "payment")
    payment.evidence_data = EvidenceData(
        attachment_id=payment.id,
        doc_type="payment",
        recognizer="bank_transaction",
        raw_text="酒店付款 2026年11月1日",
    )
    session.commit()

    assert backfill_lodging_dates(session) == 1
    assert order.evidence_data.details["check_in"] == "2026-11-02"
    assert order.evidence_data.details["check_out"] == "2026-11-04"
    assert order.evidence_data.occurred_on == date(2026, 11, 8)
    assert payment.evidence_data.details is None or payment.evidence_data.details == {}


def test_only_issue_date_does_not_create_a_stay(session):
    expense = _expense(session, date(2026, 11, 9))
    invoice = _attachment(session, expense, 5, "invoice")
    invoice.invoice_data = InvoiceData(
        attachment_id=invoice.id,
        issued_on=date(2026, 11, 9),
        item_summary="住宿费",
        tax_category="住宿服务",
        raw_text="开票日期 2026年11月9日\n房费 200元",
    )
    session.commit()

    assert backfill_lodging_dates(session) == 0
    assert invoice.invoice_data.details is None or invoice.invoice_data.details == {}


def test_issue_year_does_not_supply_missing_stay_year(session):
    expense = _expense(session, date(2027, 1, 9))
    invoice = _attachment(session, expense, 9, "invoice")
    invoice.invoice_data = InvoiceData(
        attachment_id=invoice.id,
        issued_on=date(2027, 1, 9),
        item_summary="住宿费",
        tax_category="住宿服务",
        raw_text="开票日期 2027年1月9日\n住宿日期 12月31日\n离店 1月1日",
    )
    session.commit()

    assert backfill_lodging_dates(session) == 0
    assert invoice.invoice_data.details is None or invoice.invoice_data.details == {}


def test_existing_checkin_and_nights_infers_checkout(session):
    expense = _expense(session, date(2026, 11, 1))
    order = _attachment(session, expense, 6, "order")
    order.evidence_data = EvidenceData(
        attachment_id=order.id,
        doc_type="order",
        recognizer="hotel_booking",
        details={"check_in": "2026-11-01", "nights": "3"},
    )
    session.commit()

    assert backfill_lodging_dates(session) == 1
    assert order.evidence_data.details["check_out"] == "2026-11-04"
    assert order.evidence_data.occurred_on == date(2026, 11, 1)


def test_existing_checkin_can_use_explicit_checkout_in_old_text(session):
    expense = _expense(session, date(2026, 11, 1))
    order = _attachment(session, expense, 10, "order")
    order.evidence_data = EvidenceData(
        attachment_id=order.id,
        doc_type="order",
        recognizer="hotel_booking",
        raw_text="酒店订单\n离店日期 2026年11月5日",
        details={"check_in": "2026-11-01"},
    )
    session.commit()

    assert backfill_lodging_dates(session) == 1
    assert order.evidence_data.details["check_out"] == "2026-11-05"
    assert order.evidence_data.details["nights"] == "4"


def test_old_generic_order_with_explicit_hotel_stay_is_backfilled(session):
    expense = _expense(session, date(2026, 11, 1))
    order = _attachment(session, expense, 7, "order")
    order.evidence_data = EvidenceData(
        attachment_id=order.id,
        doc_type="order",
        recognizer="filename",
        raw_text="酒店订单\n入住日期 2026年11月1日\n离店日期 2026年11月2日",
    )
    session.commit()

    assert backfill_lodging_dates(session) == 1
    assert order.evidence_data.details["check_in"] == "2026-11-01"
    assert item_from_attachment(order).is_hotel_order


def test_open_business_db_runs_backfill_once_for_existing_ledger(settings):
    engine, factory = open_business_db(settings)
    with factory() as session:
        expense = _expense(session, date(2026, 11, 9))
        order = _attachment(session, expense, 8, "order")
        order.evidence_data = EvidenceData(
            attachment_id=order.id,
            doc_type="order",
            recognizer="hotel_booking",
            raw_text="酒店水单\n住宿日期 2026年11月1日\n共2晚",
        )
        session.commit()
        attachment_id = order.id
        expense_id = expense.id
    engine.dispose()

    engine, factory = open_business_db(settings)
    with factory() as session:
        row = session.get(EvidenceData, attachment_id)
        assert row.details["check_in"] == "2026-11-01"
        assert row.details["check_out"] == "2026-11-03"
        assert row.details["nights"] == "2"
    engine.dispose()

    with TestClient(create_app(settings)) as client:
        detail = client.get(f"/api/expenses/{expense_id}").json()["data"]
    assert detail["stay_check_in"] == "2026-11-01"
    assert detail["stay_check_out"] == "2026-11-03"
    assert detail["travel_dates_missing"] is False
