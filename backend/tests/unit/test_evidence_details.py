"""details 写入：发票解析结果 → InvoiceData.details，凭证识别结果 → EvidenceData.details。"""

from pathlib import Path

from invoice_sorting.attachments.evidence_records import apply_evidence
from invoice_sorting.db.models import Attachment
from invoice_sorting.evidence.base import RecognizedEvidence
from invoice_sorting.importer.suggestions import invoice_data_from
from invoice_sorting.parsers import parse_invoice_file

INVOICES = Path(__file__).resolve().parents[1] / "fixtures" / "invoices"


def test_invoice_data_from_writes_travel_details() -> None:
    parsed = parse_invoice_file(INVOICES / "rail_ticket.pdf")
    assert parsed is not None
    data = invoice_data_from(parsed)
    assert data.details is not None
    assert data.details["vehicle"] == "train"
    assert data.details["number"] == "G7"


def test_invoice_data_from_plain_invoice_has_empty_details() -> None:
    parsed = parse_invoice_file(INVOICES / "digital_same_line.pdf")
    assert parsed is not None
    assert invoice_data_from(parsed).details == {}


def test_apply_evidence_writes_and_replaces_details() -> None:
    attachment = Attachment()
    details = {"city": "苏州", "check_in": "2026-08-15"}
    recognized = RecognizedEvidence(doc_type="order", recognizer="hotel_booking", details=details)
    evidence = apply_evidence(attachment, recognized)
    assert evidence.details == details
    assert evidence.details is not details
    again = apply_evidence(attachment, RecognizedEvidence(doc_type="unknown", recognizer="none"))
    assert again is evidence
    assert evidence.details == {}
