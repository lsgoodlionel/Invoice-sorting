"""凭证项：把发票（InvoiceData/ParsedInvoice）与非发票凭证（EvidenceData）统一成分组与匹配的输入。"""

import re
from dataclasses import dataclass, field
from datetime import date

from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.db.models import Attachment, EvidenceData, InvoiceData
from invoice_sorting.db.seed import LODGING_KEYWORDS
from invoice_sorting.importer.cities import find_city, normalize_city
from invoice_sorting.importer.platforms import platform_tokens
from invoice_sorting.parsers import ParsedInvoice

CNY = "CNY"
MIN_FILE_KEY_CHARS = 4
ORDER_NO_NOISE = re.compile(r"[\s\-_:：#]+")
ORDER_LIKE_KINDS = frozenset({AttachmentKind.INVOICE, AttachmentKind.ORDER})
HOTEL_BOOKING_RECOGNIZER = "hotel_booking"
DOC_ITINERARY = "itinerary"
TRANSPORT_WORDS = ("旅客运输", "客运", "铁路", "航空", "机票", "船票", "汽车票")
ROUTE_KEYS = ("date", "from", "to")
# 发票解析器名 → 交通工具（旧解析结果只有 travel，没有 vehicle）
PARSER_VEHICLES = {"rail_ticket": "train", "air_itinerary": "flight"}
TRAVEL_KEYS = ("date", "from", "to", "vehicle", "number", "passenger")


@dataclass(frozen=True)
class Stay:
    """住宿区间与城市；只有发票时入住、离店都取开票日期。"""

    check_in: date | None
    check_out: date | None
    city: str


def parse_day(value: str | None) -> date | None:
    try:
        return date.fromisoformat((value or "").strip()) if value else None
    except ValueError:
        return None


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


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
    doc_type: str = ""  # 凭证识别的 doc_type（发票为空）
    details: dict[str, str] = field(default_factory=dict, hash=False)  # 见差旅住宿凭证设计第 2 节

    def detail(self, key: str) -> str:
        return str(self.details.get(key) or "").strip()

    @property
    def is_lodging_invoice(self) -> bool:
        text = f"{self.tax_category} {self.item_name} {self.merchant}"
        return self.is_invoice and _contains_any(text, LODGING_KEYWORDS)

    @property
    def is_transport(self) -> bool:
        if self.kind == AttachmentKind.TRANSPORT or self.detail("vehicle"):
            return True
        if self.is_invoice and _contains_any(
            f"{self.tax_category} {self.item_name}", TRANSPORT_WORDS
        ):
            return True
        return self.doc_type == DOC_ITINERARY and all(self.detail(key) for key in ROUTE_KEYS)

    @property
    def is_hotel_order(self) -> bool:
        if self.is_invoice:
            return False
        return self.recognizer == HOTEL_BOOKING_RECOGNIZER or bool(self.detail("check_in"))

    @property
    def hotel_name(self) -> str:
        return self.detail("hotel") or self.merchant

    @property
    def stay(self) -> Stay | None:
        if self.is_hotel_order:
            city = normalize_city(self.detail("city")) or find_city(self.hotel_name)
            check_in = parse_day(self.detail("check_in"))
            return Stay(check_in, parse_day(self.detail("check_out")) or check_in, city)
        if self.is_lodging_invoice:
            return Stay(self.occurred_on, self.occurred_on, find_city(self.merchant))
        return None

    @property
    def travel_date(self) -> date | None:
        return parse_day(self.detail("date")) or self.occurred_on

    @property
    def route(self) -> tuple[str, str]:
        return self.detail("from"), self.detail("to")

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


def travel_details(travel: dict | None, parser: str = "") -> dict[str, str]:
    """ParsedInvoice.travel → details：车次/航班号记为 number，交通工具按解析器推断。"""
    source = {key: str(value).strip() for key, value in (travel or {}).items() if value}
    if not source:
        return {}
    source.setdefault("number", source.get("train_or_flight", ""))
    source.setdefault("vehicle", PARSER_VEHICLES.get(parser, ""))
    return {key: source[key] for key in TRAVEL_KEYS if source.get(key)}


def invoice_details(invoice: InvoiceData | ParsedInvoice) -> dict[str, str]:
    """发票 details：优先已保存的 details（旧库可能为 NULL），否则由解析结果的 travel 转换。"""
    stored = getattr(invoice, "details", None)
    if stored:
        return {str(key): str(value) for key, value in stored.items() if value not in (None, "")}
    return travel_details(getattr(invoice, "travel", None), invoice.parser or "")


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
        "details": invoice_details(invoice),
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
        "doc_type": evidence.doc_type or "",
        "details": {str(k): str(v) for k, v in (evidence.details or {}).items() if v},
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
