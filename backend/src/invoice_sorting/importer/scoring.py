"""M3 评分（设计 5.2）：纯函数，输入组画像与候选记录，输出分数与中文依据。"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from invoice_sorting.attachments.serializers import kind_label
from invoice_sorting.common.constants import AttachmentKind, ChecklistLevel, ChecklistState
from invoice_sorting.db.models import Expense
from invoice_sorting.importer.items import CNY, EvidenceItem
from invoice_sorting.importer.merchants import merchants_overlap
from invoice_sorting.importer.platforms import platform_tokens

SCORE_AMOUNT = 40
SCORE_DATE_CLOSE = 30
SCORE_DATE_NEAR = 15
SCORE_MERCHANT = 20
SCORE_FILLS_MISSING = 10
PENALTY_SAME_KIND = 30
DATE_CLOSE_DAYS = 3
DATE_NEAR_DAYS = 7
MATCH_THRESHOLD = 70
MATCH_LEAD = 15


@dataclass(frozen=True)
class GroupProfile:
    kinds: frozenset[str]
    amount_cents: int | None  # 人民币
    currency: str
    original_amount_cents: int | None
    occurred_on: date | None
    merchants: tuple[tuple[str, frozenset[str]], ...]  # (商家, 平台)


@dataclass(frozen=True)
class MatchCandidate:
    expense: Expense
    score: int
    reasons: tuple[str, ...]


KIND_PRIORITY = {AttachmentKind.INVOICE: 0, AttachmentKind.PAYMENT: 1, AttachmentKind.ORDER: 2}


def _priority(item: EvidenceItem) -> int:
    return KIND_PRIORITY.get(item.kind, len(KIND_PRIORITY))


def build_profile(items: Sequence[EvidenceItem]) -> GroupProfile:
    ordered = sorted(items, key=_priority)
    amount = next((item.cny_cents for item in ordered if item.cny_cents is not None), None)
    occurred = next((item.occurred_on for item in ordered if item.occurred_on), None)
    foreign = next(
        (item for item in ordered if item.is_foreign_currency and item.amount_cents), None
    )
    return GroupProfile(
        kinds=frozenset(item.kind for item in items),
        amount_cents=amount,
        currency=foreign.currency if foreign else CNY,
        original_amount_cents=foreign.amount_cents if foreign else None,
        occurred_on=occurred,
        merchants=tuple((item.merchant, item.platforms) for item in items if item.merchant),
    )


def _amount_score(profile: GroupProfile, expense: Expense) -> tuple[int, str | None]:
    if profile.amount_cents is not None and profile.amount_cents == expense.amount_cents:
        return SCORE_AMOUNT, "金额相同"
    original = profile.original_amount_cents
    if original is not None and (expense.currency, expense.original_amount_cents) == (
        profile.currency,
        original,
    ):
        return SCORE_AMOUNT, "原币金额相同"
    return 0, None


def _date_score(profile: GroupProfile, expense: Expense) -> tuple[int, str | None]:
    if profile.occurred_on is None or expense.spent_on is None:
        return 0, None
    gap = abs((profile.occurred_on - expense.spent_on).days)
    reason = "日期相同" if gap == 0 else f"日期相差 {gap} 天"
    if gap <= DATE_CLOSE_DAYS:
        return SCORE_DATE_CLOSE, reason
    if gap <= DATE_NEAR_DAYS:
        return SCORE_DATE_NEAR, reason
    return 0, None


def _merchant_score(profile: GroupProfile, expense: Expense) -> tuple[int, str | None]:
    platforms = platform_tokens(expense.merchant or "", expense.summary or "")
    for merchant, item_platforms in profile.merchants:
        if merchants_overlap(merchant, item_platforms, expense.merchant or "", platforms):
            return SCORE_MERCHANT, "商家相同"
    return 0, None


def missing_kinds(expense: Expense) -> list[str]:
    """记录必需且缺少的凭证类型（按清单项 id 排序）。"""
    items = sorted(expense.checklist_items, key=lambda item: item.id or 0)
    return [
        item.attachment_kind
        for item in items
        if item.level == ChecklistLevel.REQUIRED and item.state == ChecklistState.MISSING
    ]


def _kind_scores(profile: GroupProfile, expense: Expense) -> list[tuple[int, str]]:
    scores: list[tuple[int, str]] = []
    missing = [kind for kind in missing_kinds(expense) if kind in profile.kinds]
    if missing:
        labels = "、".join(kind_label(kind) for kind in missing)
        scores.append((SCORE_FILLS_MISSING, f"正好缺少{labels}"))
    present = sorted({a.kind for a in expense.attachments} & profile.kinds)
    if present:
        labels = "、".join(kind_label(kind) for kind in present)
        scores.append((-PENALTY_SAME_KIND, f"已有{labels}"))
    return scores


def score_expense(profile: GroupProfile, expense: Expense) -> MatchCandidate:
    parts = [
        _amount_score(profile, expense),
        _date_score(profile, expense),
        _merchant_score(profile, expense),
        *_kind_scores(profile, expense),
    ]
    score = sum(points for points, _reason in parts)
    reasons = tuple(reason for _points, reason in parts if reason)
    return MatchCandidate(expense, score, reasons)


def pick_match(ranked: Sequence[MatchCandidate]) -> MatchCandidate | None:
    """最高分 ≥ 70 且领先第二名 ≥ 15 才算强匹配。"""
    if not ranked or ranked[0].score < MATCH_THRESHOLD:
        return None
    if len(ranked) > 1 and ranked[0].score - ranked[1].score < MATCH_LEAD:
        return None
    return ranked[0]
