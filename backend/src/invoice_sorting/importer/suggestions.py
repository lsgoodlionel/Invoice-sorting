"""由解析结果生成发票数据、建议字段与提示信息。"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from invoice_sorting.attachments.serializers import is_buyer_mismatch
from invoice_sorting.checklist.regions import (
    DEFAULT_POLICY,
    RegionPolicy,
    is_detail_seller,
    is_nonlocal_region,
)
from invoice_sorting.common.platforms import ONLINE_PLATFORM_KEYWORDS
from invoice_sorting.db.models import InvoiceData
from invoice_sorting.importer.classify import suggest_category
from invoice_sorting.parsers import ParsedInvoice
from invoice_sorting.parsers.travel_details import travel_details

RAW_TEXT_LIMIT = 20000
BUYER_MISMATCH_WARNING = "购方名称或税号与设置不一致，请核对发票抬头"
MISSING_AMOUNT_WARNING = "未识别到金额，请手工填写"
MISSING_DATE_WARNING = "未识别到开票日期，请手工填写"
MISSING_SELLER_WARNING = "未识别到销售方，请手工填写商家"
MISSING_NUMBER_WARNING = "未识别到发票号码，无法按号码判重"
NONLOCAL_WARNING = "外地发票（{region}）：需附网购订单截图，已带明细平台可免"


@dataclass(frozen=True)
class Suggestion:
    spent_on: date | None
    amount_cents: int | None
    merchant: str
    summary: str
    category_id: int | None
    is_online: bool = False


def invoice_data_from(parsed: ParsedInvoice) -> InvoiceData:
    return InvoiceData(
        invoice_no=parsed.invoice_no,
        issued_on=parsed.issued_on,
        total_cents=parsed.total_cents,
        tax_cents=parsed.tax_cents,
        seller_name=parsed.seller_name or "",
        seller_tax_id=parsed.seller_tax_id or "",
        buyer_name=parsed.buyer_name or "",
        buyer_tax_id=parsed.buyer_tax_id or "",
        item_summary=parsed.item_summary or "",
        invoice_type=parsed.invoice_type or "",
        tax_category=parsed.tax_category or "",
        region_name=parsed.region_name or "",
        order_no=parsed.order_no or "",
        parser=parsed.parser or "",
        confirmed=False,
        raw_text=(parsed.raw_text or "")[:RAW_TEXT_LIMIT],
        details=travel_details(parsed),
    )


def suggested_spent_on(parsed: ParsedInvoice) -> date | None:
    """差旅票优先取乘车/乘机日期，否则取开票日期。"""
    travel_date = (parsed.travel or {}).get("date", "")
    try:
        return date.fromisoformat(travel_date) if travel_date else parsed.issued_on
    except ValueError:
        return parsed.issued_on


def is_online_purchase(order_no: str | None, seller_name: str | None) -> bool:
    """有订单号，或销售方名称包含电商平台关键词。"""
    return bool((order_no or "").strip()) or is_detail_seller(seller_name, ONLINE_PLATFORM_KEYWORDS)


def build_suggestion(session: Session, parsed: ParsedInvoice) -> Suggestion:
    return Suggestion(
        spent_on=suggested_spent_on(parsed),
        amount_cents=parsed.total_cents,
        merchant=parsed.seller_name or "",
        summary=parsed.item_summary or "",
        category_id=suggest_category(
            session, parsed.seller_name, parsed.item_summary, parsed.tax_category
        ),
        is_online=is_online_purchase(parsed.order_no, parsed.seller_name),
    )


def suggestion_from_invoice(session: Session, invoice: InvoiceData) -> Suggestion:
    """由已入库的发票数据生成建议（用于待归属发票批量生成记录）。"""
    return Suggestion(
        spent_on=invoice.issued_on,
        amount_cents=invoice.total_cents,
        merchant=invoice.seller_name or "",
        summary=invoice.item_summary or "",
        category_id=suggest_category(
            session, invoice.seller_name, invoice.item_summary, invoice.tax_category
        ),
        is_online=is_online_purchase(invoice.order_no, invoice.seller_name),
    )


def nonlocal_warning(invoice: InvoiceData, policy: RegionPolicy) -> str | None:
    """外地发票且销售方不属于已带明细平台时，提示需附订单截图。"""
    if not is_nonlocal_region(invoice.region_name, policy.local_region):
        return None
    if is_detail_seller(invoice.seller_name, policy.detail_platforms):
        return None
    return NONLOCAL_WARNING.format(region=invoice.region_name)


def build_warnings(
    parsed: ParsedInvoice,
    invoice: InvoiceData,
    buyer: tuple[str, str] | None,
    policy: RegionPolicy = DEFAULT_POLICY,
) -> list[str]:
    warnings = list(parsed.warnings)
    if is_buyer_mismatch(invoice, buyer):
        warnings.append(BUYER_MISMATCH_WARNING)
    nonlocal_message = nonlocal_warning(invoice, policy)
    if nonlocal_message:
        warnings.append(nonlocal_message)
    missing = (
        (parsed.total_cents is None, MISSING_AMOUNT_WARNING),
        (suggested_spent_on(parsed) is None, MISSING_DATE_WARNING),
        (not parsed.seller_name, MISSING_SELLER_WARNING),
        (not parsed.invoice_no, MISSING_NUMBER_WARNING),
    )
    warnings.extend(message for is_missing, message in missing if is_missing)
    return list(dict.fromkeys(warnings))
