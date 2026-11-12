"""发票的开票日期、实际业务发生日期与关联日期。"""

from collections.abc import Mapping
from datetime import date


def _structured_date(invoice: object, attribute: str) -> date | None:
    values = getattr(invoice, attribute, None)
    if not isinstance(values, Mapping):
        return None
    value = values.get("date")
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def invoice_business_date(invoice: object) -> date | None:
    """票面结构化信息中的实际业务日期；没有识别到时返回 None。"""
    return _structured_date(invoice, "details") or _structured_date(invoice, "travel")


def invoice_effective_date(invoice: object) -> date | None:
    """用于建账和关联：实际业务日期优先，无法识别时才回退开票日期。"""
    business_date = invoice_business_date(invoice)
    if business_date is not None:
        return business_date
    issued_on = getattr(invoice, "issued_on", None)
    return issued_on if isinstance(issued_on, date) else None
