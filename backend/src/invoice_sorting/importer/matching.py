"""发票与“已支出”记录的匹配（蓝图 5.1：金额 + 日期 ±7 天 + 商家）。"""

import re
from datetime import date, timedelta

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from invoice_sorting.common.constants import AttachmentKind, ExpenseStatus
from invoice_sorting.db.models import Attachment, Expense

MATCH_WINDOW_DAYS = 7
CONTAINMENT_BONUS = 1000
COMPANY_SUFFIXES = re.compile(r"(股份有限公司|有限责任公司|有限公司|公司|商行|店)$")
WHITESPACE = re.compile(r"\s+")


def _normalize_merchant(name: str) -> str:
    text = WHITESPACE.sub("", name or "").lower()
    return COMPANY_SUFFIXES.sub("", text)


def _longest_common_substring(first: str, second: str) -> int:
    best = 0
    previous = [0] * (len(second) + 1)
    for char in first:
        current = [0] * (len(second) + 1)
        for index, other in enumerate(second, start=1):
            if char == other:
                current[index] = previous[index - 1] + 1
                best = max(best, current[index])
        previous = current
    return best


def merchant_similarity(first: str, second: str) -> int:
    """包含关系得分最高（加上较短名称长度），否则为最长公共子串长度。"""
    left, right = _normalize_merchant(first), _normalize_merchant(second)
    if not left or not right:
        return 0
    if left in right or right in left:
        return CONTAINMENT_BONUS + min(len(left), len(right))
    return _longest_common_substring(left, right)


def _candidates(session: Session, amount_cents: int, spent_on: date) -> list[Expense]:
    window = timedelta(days=MATCH_WINDOW_DAYS)
    has_invoice = exists().where(
        Attachment.expense_id == Expense.id, Attachment.kind == str(AttachmentKind.INVOICE)
    )
    query = select(Expense).where(
        Expense.status == str(ExpenseStatus.SPENT),
        Expense.deleted.is_(False),
        Expense.amount_cents == amount_cents,
        Expense.spent_on.between(spent_on - window, spent_on + window),
        ~has_invoice,
    )
    return list(session.scalars(query))


def find_spent_match(
    session: Session, amount_cents: int | None, spent_on: date | None, merchant: str
) -> Expense | None:
    """返回最匹配的“已支出”记录：商家更相似者优先，其次日期差最小，再按 id。"""
    if amount_cents is None or spent_on is None:
        return None
    candidates = _candidates(session, amount_cents, spent_on)
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (
            -merchant_similarity(item.merchant, merchant),
            abs((item.spent_on - spent_on).days),
            item.id,
        ),
    )
