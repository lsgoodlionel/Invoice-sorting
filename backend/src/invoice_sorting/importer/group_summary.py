"""组摘要（设计 5.2“建议新建时的字段来源”）：发票 > 人民币支付记录 > 订单/收据。

金额与日期按上述顺序取第一个非空值；商家与摘要取“发票 > 订单/收据 > 支付记录”（银行交易的商户描述
如 PP*APPLE.COM/BILL 不适合作为商家名）。无发票且境外或外币 → 免发票。
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.attachments import evidence_records
from invoice_sorting.checklist.regions import is_detail_seller
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.db.models import Category
from invoice_sorting.importer.classify import suggest_category
from invoice_sorting.importer.items import CNY, ORDER_LIKE_KINDS, EvidenceItem
from invoice_sorting.importer.suggestions import ONLINE_PLATFORM_KEYWORDS

# 文件名首段分类词 → 默认分类名（找不到同名未归档分类时走分类建议逻辑）
CATEGORY_WORDS: dict[str, str] = {
    "办公": "办公用品",
    "软件": "软件服务",
    "打车": "差旅交通",
    "出行": "差旅交通",
    "交通": "差旅交通",
    "差旅": "差旅交通",
    "线缆": "易耗品",
    "数码": "易耗品",
    "数据": "易耗品",
    "耗材": "易耗品",
    "图书": "图书",
    "设备": "设备",
}


@dataclass(frozen=True)
class GroupSummary:
    spent_on: date | None
    amount_cents: int | None  # 人民币
    currency: str
    original_amount_cents: int | None
    merchant: str
    summary: str
    category_id: int | None
    is_online: bool
    invoice_exempt: bool


def _by_kind(items: Iterable[EvidenceItem], kind: AttachmentKind) -> list[EvidenceItem]:
    return [item for item in items if item.kind == kind]


def _first(sources: Iterable[EvidenceItem], getter: Callable[[EvidenceItem], Any]) -> Any:
    """按来源顺序取第一个非空值（None 与空串视为空）。"""
    return next((value for item in sources if (value := getter(item)) not in (None, "")), None)


def _ordered(items: tuple[EvidenceItem, ...]) -> tuple[list, list]:
    invoices = _by_kind(items, AttachmentKind.INVOICE)
    payments = [item for item in _by_kind(items, AttachmentKind.PAYMENT) if item.cny_cents]
    orders = _by_kind(items, AttachmentKind.ORDER)
    rest = [item for item in items if item not in invoices + payments + orders]
    return invoices + payments + orders + rest, invoices + orders + payments + rest


def _original_amount(items: tuple[EvidenceItem, ...]) -> tuple[str, int | None]:
    foreign = [item for item in items if item.is_foreign_currency and item.amount_cents]
    foreign.sort(key=lambda item: item.kind != AttachmentKind.ORDER)
    if not foreign:
        return CNY, None
    return foreign[0].currency, foreign[0].amount_cents


def is_exempt(items: tuple[EvidenceItem, ...]) -> bool:
    if any(item.is_invoice for item in items):
        return False
    return any(item.is_foreign or item.is_foreign_currency for item in items)


def _is_online(items: tuple[EvidenceItem, ...], merchant: str) -> bool:
    if any(item.order_key for item in items if item.kind in ORDER_LIKE_KINDS):
        return True
    return is_detail_seller(merchant, ONLINE_PLATFORM_KEYWORDS)


def category_from_filenames(session: Session, items: tuple[EvidenceItem, ...]) -> int | None:
    for item in items:
        hints = evidence_records.safe_filename_hints(item.original_name)
        word = (hints.category_word or "").strip() if hints is not None else ""
        name = CATEGORY_WORDS.get(word, word)
        if not name:
            continue
        query = select(Category.id).where(Category.name == name, Category.archived.is_(False))
        category_id = session.scalar(query)
        if category_id is not None:
            return category_id
    return None


def suggest_group_category(
    session: Session, items: tuple[EvidenceItem, ...], merchant: str, summary: str
) -> int | None:
    tax_category = _first(items, lambda item: item.tax_category) or ""
    from_name = category_from_filenames(session, items)
    return suggest_category(session, merchant, summary, tax_category, from_name)


def build_summary(session: Session, items: tuple[EvidenceItem, ...]) -> GroupSummary:
    by_amount, by_name = _ordered(items)
    merchant = _first(by_name, lambda item: item.merchant) or ""
    summary = _first(by_name, lambda item: item.item_name) or ""
    currency, original = _original_amount(items)
    return GroupSummary(
        spent_on=_first(by_amount, lambda item: item.occurred_on),
        amount_cents=_first(by_amount, lambda item: item.cny_cents),
        currency=currency,
        original_amount_cents=original,
        merchant=merchant,
        summary=summary,
        category_id=suggest_group_category(session, items, merchant, summary),
        is_online=_is_online(items, merchant),
        invoice_exempt=is_exempt(items),
    )
