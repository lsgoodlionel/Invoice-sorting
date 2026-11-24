"""根据订单与发票项目文字推导数量、单价；人工设置后不再自动覆盖。"""

import re
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.db.models import Attachment, Expense

MIN_QUANTITY = 1
MAX_QUANTITY = 100
UNIT_WORDS = "件|个|套|盒|包|本|台|张|份|支|瓶|组|只|条|箱|袋|册|卷|副|双"
QUANTITY_PATTERNS = (
    re.compile(rf"(?:数量|共|合计)\s*[:：]?\s*(\d{{1,3}})\s*(?:{UNIT_WORDS})?"),
    re.compile(r"(?:×|x|X|\*)\s*(\d{1,3})(?!\d)"),
    re.compile(rf"(?<!\d)(\d{{1,3}})\s*(?:{UNIT_WORDS})(?:装)?(?!\d)"),
)


def infer_quantity(texts: list[str]) -> int:
    """只识别带明确数量语义的 1–100，普通型号、日期和订单号不会命中。"""
    for text in texts:
        for pattern in QUANTITY_PATTERNS:
            match = pattern.search(text or "")
            if match:
                value = int(match.group(1))
                if MIN_QUANTITY <= value <= MAX_QUANTITY:
                    return value
    return 1


def pricing_texts(expense: Expense) -> list[str]:
    """订单项目优先，其次发票项目，再使用记录名称与摘要。"""
    orders: list[str] = []
    invoices: list[str] = []
    for attachment in sorted(expense.attachments, key=lambda item: item.id):
        if attachment.kind == AttachmentKind.ORDER and attachment.evidence_data is not None:
            orders.append(attachment.evidence_data.item_name or "")
        if attachment.kind == AttachmentKind.INVOICE and attachment.invoice_data is not None:
            invoices.append(attachment.invoice_data.item_summary or "")
    return [*orders, *invoices, expense.item_name or "", expense.summary or ""]


def inferred_item_name(expense: Expense) -> str:
    """名称统一优先级：人工/已有名称 → 订单 → 发票 → 摘要 → 商家。"""
    if expense.item_name.strip():
        return expense.item_name.strip()
    orders: list[str] = []
    invoices: list[str] = []
    for attachment in sorted(expense.attachments, key=lambda item: item.id):
        if attachment.kind == AttachmentKind.ORDER and attachment.evidence_data is not None:
            orders.append(attachment.evidence_data.item_name or "")
        if attachment.kind == AttachmentKind.INVOICE and attachment.invoice_data is not None:
            invoices.append(attachment.invoice_data.item_summary or "")
    return next(
        (
            text.strip()
            for text in [*orders, *invoices, expense.summary, expense.merchant]
            if text.strip()
        ),
        "",
    )


def _unit_price(amount_cents: int, quantity: int) -> int:
    return int(
        (Decimal(amount_cents) / Decimal(quantity)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def apply_default_pricing(expense: Expense) -> None:
    """未人工设置时填数量与单价；分不能整除时按人民币分四舍五入。"""
    if expense.pricing_manual:
        return
    quantity = infer_quantity(pricing_texts(expense))
    expense.quantity = quantity
    expense.unit_price_cents = _unit_price(expense.amount_cents, quantity)


def backfill_expense_display_fields(session: Session) -> int:
    """升级时只补历史空值；已有名称、数量或单价绝不覆盖。"""
    rows = session.scalars(
        select(Expense)
        .where(
            Expense.deleted.is_(False),
            or_(
                Expense.item_name == "",
                Expense.quantity.is_(None),
                Expense.unit_price_cents.is_(None),
            ),
        )
        .options(
            selectinload(Expense.attachments).selectinload(Attachment.invoice_data),
            selectinload(Expense.attachments).selectinload(Attachment.evidence_data),
        )
    )
    changed = 0
    for expense in rows:
        touched = False
        if not expense.item_name.strip():
            expense.item_name = inferred_item_name(expense)
            touched = bool(expense.item_name)
        if expense.quantity is None:
            expense.quantity = infer_quantity(pricing_texts(expense))
            touched = True
        if expense.unit_price_cents is None:
            expense.unit_price_cents = _unit_price(expense.amount_cents, expense.quantity or 1)
            touched = True
        changed += int(touched)
    session.commit()
    return changed
