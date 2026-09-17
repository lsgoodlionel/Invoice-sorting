"""凭证组与已有记录匹配（设计 5.2）：M1 订单号 → M2 文件名键 → M3 评分。

候选范围：未删除、非作废、不在已外发批次中的记录。
"""

from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.orm import Session

from invoice_sorting.common.constants import BatchStatus, ExpenseStatus
from invoice_sorting.db.models import Attachment, Batch, EvidenceData, Expense, InvoiceData
from invoice_sorting.importer.items import EvidenceItem, item_from_attachment
from invoice_sorting.importer.merchants import merchant_similarity
from invoice_sorting.importer.scoring import (
    DATE_NEAR_DAYS,
    GroupProfile,
    MatchCandidate,
    build_profile,
    pick_match,
    score_expense,
)

__all__ = [
    "MatchCandidate",
    "candidates_for_attachment",
    "find_candidates",
    "merchant_similarity",
    "normalized_order_column",
]

STRONG_SCORE = 100
MIN_CANDIDATE_SCORE = 45
MAX_CANDIDATES = 5
REASON_ORDER_NO = "订单号一致"
REASON_FILE_KEY = "文件名一致"
ORDER_NO_NOISE_CHARS = (" ", "-", "_", ":", "：", "#")


def normalized_order_column(column: ColumnElement[str]) -> ColumnElement[str]:
    """SQL 侧与 items.normalize_order_no 相同的规范化。"""
    expression = column
    for char in ORDER_NO_NOISE_CHARS:
        expression = func.replace(expression, char, "")
    return func.upper(expression)


def eligible_condition() -> ColumnElement[bool]:
    sent_batches = select(Batch.id).where(Batch.status != str(BatchStatus.DRAFT))
    return and_(
        Expense.deleted.is_(False),
        Expense.status != str(ExpenseStatus.VOID),
        or_(Expense.batch_id.is_(None), Expense.batch_id.not_in(sent_batches)),
    )


def _by_order_no(session: Session, keys: set[str]) -> list[Expense]:
    found: dict[int, Expense] = {}
    for model in (InvoiceData, EvidenceData):
        query = (
            select(Expense)
            .join(Attachment, Attachment.expense_id == Expense.id)
            .join(model, model.attachment_id == Attachment.id)
            .where(eligible_condition(), normalized_order_column(model.order_no).in_(keys))
        )
        found.update((expense.id, expense) for expense in session.scalars(query))
    return [found[key] for key in sorted(found)]


def _by_file_key(session: Session, keys: set[str]) -> list[Expense]:
    query = (
        select(Expense)
        .join(Attachment, Attachment.expense_id == Expense.id)
        .where(eligible_condition(), Attachment.file_key.in_(keys))
        .distinct()
        .order_by(Expense.id)
    )
    return list(session.scalars(query))


def _score_pool(session: Session, profile: GroupProfile) -> list[Expense]:
    options: list[ColumnElement[bool]] = []
    if profile.amount_cents is not None:
        options.append(Expense.amount_cents == profile.amount_cents)
    if profile.original_amount_cents is not None:
        options.append(Expense.original_amount_cents == profile.original_amount_cents)
    if profile.occurred_on is not None:
        window = timedelta(days=DATE_NEAR_DAYS)
        start, end = profile.occurred_on - window, profile.occurred_on + window
        options.append(Expense.spent_on.between(start, end))
    if not options:
        return []
    query = select(Expense).where(eligible_condition(), or_(*options)).order_by(Expense.id)
    return list(session.scalars(query))


def _rank(profile: GroupProfile, expenses: list[Expense]) -> list[MatchCandidate]:
    scored = [score_expense(profile, expense) for expense in expenses]
    kept = [item for item in scored if item.score >= MIN_CANDIDATE_SCORE]

    def sort_key(item: MatchCandidate) -> tuple[int, int, int]:
        gap = abs((profile.occurred_on - item.expense.spent_on).days) if profile.occurred_on else 0
        return (-item.score, gap, item.expense.id)

    return sorted(kept, key=sort_key)


def _strong(expenses: list[Expense], reason: str) -> list[MatchCandidate]:
    return [MatchCandidate(expense, STRONG_SCORE, (reason,)) for expense in expenses]


def _strong_matches(session: Session, items: Sequence[EvidenceItem]) -> list[MatchCandidate]:
    order_keys = {item.order_key for item in items if item.order_key}
    if order_keys and (expenses := _by_order_no(session, order_keys)):
        return _strong(expenses, REASON_ORDER_NO)
    file_keys = {item.usable_file_key for item in items if item.usable_file_key}
    if file_keys and (expenses := _by_file_key(session, file_keys)):
        return _strong(expenses, REASON_FILE_KEY)
    return []


def find_candidates(
    session: Session, items: Sequence[EvidenceItem]
) -> tuple[MatchCandidate | None, list[MatchCandidate]]:
    """返回 (强匹配或 None, 其他候选最多 5 个，按分数降序)。"""
    if not items:
        return None, []
    session.flush()
    strong = _strong_matches(session, items)
    profile = build_profile(items)
    strong_ids = {candidate.expense.id for candidate in strong}
    scored = [
        candidate
        for candidate in _rank(profile, _score_pool(session, profile))
        if candidate.expense.id not in strong_ids
    ]
    if len(strong) == 1:
        return strong[0], scored[:MAX_CANDIDATES]
    if strong:
        return None, (strong + scored)[:MAX_CANDIDATES]
    match = pick_match(scored)
    others = [candidate for candidate in scored if candidate is not match]
    return match, others[:MAX_CANDIDATES]


def candidates_for_attachment(session: Session, attachment: Attachment) -> list[MatchCandidate]:
    """单个待归属附件的候选记录：强匹配在前，其余按分数降序。"""
    match, others = find_candidates(session, [item_from_attachment(attachment)])
    return ([match] if match is not None else []) + others
