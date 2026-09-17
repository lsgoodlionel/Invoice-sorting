"""附件与发票数据的接口形状（docs/api-contract.md: Attachment / InvoiceData）。"""

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from invoice_sorting.checklist.regions import (
    DEFAULT_POLICY,
    RegionPolicy,
    is_detail_seller,
    is_nonlocal_region,
)
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.db.models import TZ, Attachment, EvidenceData, InvoiceData

WHITESPACE = re.compile(r"\s+")
FULLWIDTH_PARENS = str.maketrans({"（": "(", "）": ")"})


def iso_datetime(value: datetime | None) -> str | None:
    """SQLite 读回的时间不带时区，统一按 Asia/Shanghai 输出 ISO 8601。"""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=TZ)
    return value.isoformat()


def iso_date(value: date | None) -> str | None:
    return value.isoformat() if value else None


def kind_label(kind: str) -> str:
    try:
        return AttachmentKind(kind).label
    except ValueError:
        return AttachmentKind.OTHER.label


def _normalize(text: str) -> str:
    return WHITESPACE.sub("", text or "").translate(FULLWIDTH_PARENS).upper()


def is_buyer_mismatch(invoice: InvoiceData, buyer: tuple[str, str] | None) -> bool:
    """设置中的购方名称/税号任一非空，且与发票上已识别出的对应值不一致。"""
    if buyer is None:
        return False
    pairs = zip(buyer, (invoice.buyer_name, invoice.buyer_tax_id), strict=True)
    return any(
        _normalize(expected) and _normalize(actual) and _normalize(expected) != _normalize(actual)
        for expected, actual in pairs
    )


def serialize_invoice(
    invoice: InvoiceData,
    buyer: tuple[str, str] | None = None,
    policy: RegionPolicy = DEFAULT_POLICY,
) -> dict[str, Any]:
    return {
        "invoice_no": invoice.invoice_no,
        "issued_on": iso_date(invoice.issued_on),
        "total_cents": invoice.total_cents,
        "tax_cents": invoice.tax_cents,
        "seller_name": invoice.seller_name or "",
        "seller_tax_id": invoice.seller_tax_id or "",
        "buyer_name": invoice.buyer_name or "",
        "buyer_tax_id": invoice.buyer_tax_id or "",
        "item_summary": invoice.item_summary or "",
        "invoice_type": invoice.invoice_type or "",
        "tax_category": invoice.tax_category or "",
        "region_name": invoice.region_name or "",
        "is_nonlocal": is_nonlocal_region(invoice.region_name, policy.local_region),
        "order_no": invoice.order_no or "",
        "detail_platform": is_detail_seller(invoice.seller_name, policy.detail_platforms),
        "parser": invoice.parser or "",
        "confirmed": bool(invoice.confirmed),
        "buyer_mismatch": is_buyer_mismatch(invoice, buyer),
    }


def serialize_evidence(evidence: EvidenceData) -> dict[str, Any]:
    return {
        "doc_type": evidence.doc_type,
        "recognizer": evidence.recognizer or "",
        "amount_cents": evidence.amount_cents,
        "currency": evidence.currency or "CNY",
        "cny_cents": evidence.cny_cents,
        "occurred_on": iso_date(evidence.occurred_on),
        "merchant": evidence.merchant or "",
        "item_name": evidence.item_name or "",
        "order_no": evidence.order_no or "",
        "card_last4": evidence.card_last4 or "",
        "is_foreign": bool(evidence.is_foreign),
        "confirmed": bool(evidence.confirmed),
    }


def serialize_attachment(
    attachment: Attachment,
    buyer: tuple[str, str] | None = None,
    policy: RegionPolicy = DEFAULT_POLICY,
) -> dict[str, Any]:
    invoice, evidence = attachment.invoice_data, attachment.evidence_data
    return {
        "id": attachment.id,
        "expense_id": attachment.expense_id,
        "kind": attachment.kind,
        "kind_label": kind_label(attachment.kind),
        "original_name": attachment.original_name,
        "file_name": Path(attachment.file_path).name,
        "mime": attachment.mime,
        "size": attachment.size,
        "created_at": iso_datetime(attachment.created_at),
        "url": f"/api/attachments/{attachment.id}/file",
        "file_key": attachment.file_key or "",
        "invoice": serialize_invoice(invoice, buyer, policy) if invoice is not None else None,
        "evidence": serialize_evidence(evidence) if evidence is not None else None,
    }
