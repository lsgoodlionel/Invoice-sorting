"""凭证项：把发票（InvoiceData/ParsedInvoice）与非发票凭证（EvidenceData）统一成分组与匹配的输入。"""

import re
from dataclasses import dataclass
from datetime import date

from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.db.models import Attachment, EvidenceData, InvoiceData
from invoice_sorting.importer.platforms import platform_tokens
from invoice_sorting.parsers import ParsedInvoice

CNY = "CNY"
MIN_FILE_KEY_CHARS = 4
ORDER_NO_NOISE = re.compile(r"[\s\-_:：#]+")
ORDER_LIKE_KINDS = frozenset({AttachmentKind.INVOICE, AttachmentKind.ORDER})


@dataclass(frozen=True)
class EvidenceItem:
    attachment_id: int
    kind: str
    original_name: str
    file_key: str = ""
    order_no: str = ""
    amount_cents: int | None = None  # 票面金额（按 currency）
    currency: str = CNY
    cny_cents: int | None = None  # 人民币金额
    occurred_on: date | None = None
    merchant: str = ""
    item_name: str = ""
    card_last4: str = ""
    is_foreign: bool = False
    recognizer: str = ""
    tax_category: str = ""
    has_data: bool = False  # 是否有发票数据或凭证识别结果

    @property
    def is_invoice(self) -> bool:
        return self.kind == AttachmentKind.INVOICE

    @property
    def order_key(self) -> str:
        return normalize_order_no(self.order_no)

    @property
    def usable_file_key(self) -> str:
        key = (self.file_key or "").strip()
        return key if len(key) >= MIN_FILE_KEY_CHARS else ""

    @property
    def is_foreign_currency(self) -> bool:
        return (self.currency or CNY) != CNY

    @property
    def platforms(self) -> frozenset[str]:
        return platform_tokens(self.merchant, self.item_name, recognizer=self.recognizer)


def normalize_order_no(order_no: str | None) -> str:
    """忽略空白、连接符与大小写。"""
    return ORDER_NO_NOISE.sub("", order_no or "").upper()


def _invoice_fields(invoice: InvoiceData | ParsedInvoice, occurred_on: date | None) -> dict:
    return {
        "order_no": invoice.order_no or "",
        "amount_cents": invoice.total_cents,
        "cny_cents": invoice.total_cents,
        "occurred_on": occurred_on if occurred_on is not None else invoice.issued_on,
        "merchant": invoice.seller_name or "",
        "item_name": invoice.item_summary or "",
        "recognizer": invoice.parser or "",
        "tax_category": invoice.tax_category or "",
        "has_data": True,
    }


def _evidence_fields(evidence: EvidenceData) -> dict:
    currency = (evidence.currency or CNY).upper()
    cny = evidence.cny_cents
    if cny is None and currency == CNY:
        cny = evidence.amount_cents
    return {
        "order_no": evidence.order_no or "",
        "amount_cents": evidence.amount_cents,
        "currency": currency,
        "cny_cents": cny,
        "occurred_on": evidence.occurred_on,
        "merchant": evidence.merchant or "",
        "item_name": evidence.item_name or "",
        "card_last4": evidence.card_last4 or "",
        "is_foreign": bool(evidence.is_foreign),
        "recognizer": evidence.recognizer or "",
        "has_data": True,
    }


def item_from_attachment(
    attachment: Attachment,
    *,
    parsed: ParsedInvoice | None = None,
    occurred_on: date | None = None,
) -> EvidenceItem:
    """发票类型优先取发票数据（可传入解析结果与差旅日期），否则取凭证识别结果。"""
    fields: dict = {}
    is_invoice = attachment.kind == AttachmentKind.INVOICE
    invoice = parsed if parsed is not None else attachment.invoice_data
    if invoice is not None and (is_invoice or attachment.evidence_data is None):
        fields = _invoice_fields(invoice, occurred_on)
    elif attachment.evidence_data is not None:
        fields = _evidence_fields(attachment.evidence_data)
    return EvidenceItem(
        attachment_id=attachment.id,
        kind=attachment.kind,
        original_name=attachment.original_name,
        file_key=attachment.file_key or "",
        **fields,
    )
