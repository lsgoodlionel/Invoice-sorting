"""根据订单与发票项目文字推导数量、单价；人工设置后不再自动覆盖。"""

import re
from decimal import ROUND_HALF_UP, Decimal

from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.db.models import Expense

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


def apply_default_pricing(expense: Expense) -> None:
    """未人工设置时填数量与单价；分不能整除时按人民币分四舍五入。"""
    if expense.pricing_manual:
        return
    quantity = infer_quantity(pricing_texts(expense))
    unit = int(
        (Decimal(expense.amount_cents) / Decimal(quantity)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
    expense.quantity = quantity
    expense.unit_price_cents = unit
