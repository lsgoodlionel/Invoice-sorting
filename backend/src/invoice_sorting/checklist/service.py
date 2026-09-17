"""凭证清单：按分类模板与条件计算清单项，并与附件同步（蓝图 4.2 / 11）。"""

from collections.abc import Callable
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from invoice_sorting.checklist.regions import (
    DEFAULT_POLICY,
    RegionPolicy,
    is_detail_platform,
    is_nonlocal,
)
from invoice_sorting.common.constants import ChecklistLevel, ChecklistState
from invoice_sorting.db.models import Attachment, ChecklistItem, ChecklistRule, Expense
from invoice_sorting.settings.service import region_policy

HINT_SEPARATOR = "；"
LEVEL_STRENGTH = {ChecklistLevel.REQUIRED: 2, ChecklistLevel.SUGGESTED: 1}


def _flag_matches(condition: dict[str, Any], key: str, actual: Callable[[], bool]) -> bool:
    return key not in condition or actual() == bool(condition[key])


def _content_text(expense: Expense) -> str:
    """用于关键词条件的文本：记录商家与摘要，以及发票的税收分类、商品名称、销售方。"""
    parts = [expense.merchant or "", expense.summary or ""]
    for attachment in expense.attachments or []:
        invoice = attachment.invoice_data
        if invoice is not None:
            parts.extend(
                [invoice.tax_category or "", invoice.item_summary or "", invoice.seller_name or ""]
            )
    return " ".join(parts)


def _keywords_match(condition: dict[str, Any], expense: Expense) -> bool:
    """content_keywords：包含任一关键词才触发；exclude_keywords：包含任一关键词则不触发。"""
    include = [word for word in condition.get("content_keywords") or [] if word]
    exclude = [word for word in condition.get("exclude_keywords") or [] if word]
    if not include and not exclude:
        return True
    text = _content_text(expense)
    if include and not any(word in text for word in include):
        return False
    return not any(word in text for word in exclude)


def condition_matches(
    condition: dict[str, Any] | None, expense: Expense, policy: RegionPolicy = DEFAULT_POLICY
) -> bool:
    """condition 中所有键都满足才触发；空条件总是触发。policy 提供本地地区与明细平台。"""
    condition = condition or {}
    if "amount_gte" in condition and expense.amount_cents < int(condition["amount_gte"]):
        return False
    if "amount_lt" in condition and expense.amount_cents >= int(condition["amount_lt"]):
        return False
    flags = (
        ("is_online", lambda: bool(expense.is_online)),
        ("is_nonlocal", lambda: is_nonlocal(expense, policy.local_region)),
        ("detail_platform", lambda: is_detail_platform(expense, policy.detail_platforms)),
        ("invoice_exempt", lambda: bool(expense.invoice_exempt)),
    )
    if not all(_flag_matches(condition, key, actual) for key, actual in flags):
        return False
    return _keywords_match(condition, expense)


def _merge(first: ChecklistRule, second: ChecklistRule) -> ChecklistRule:
    strength = LEVEL_STRENGTH.get
    level = max(first.level, second.level, key=lambda value: strength(value, 0))
    hints = [hint for hint in first.hint.split(HINT_SEPARATOR) if hint]
    if second.hint and second.hint not in hints:
        hints.append(second.hint)
    return ChecklistRule(
        id=first.id,
        category_id=first.category_id,
        attachment_kind=first.attachment_kind,
        level=level,
        condition={},
        hint=HINT_SEPARATOR.join(hints),
    )


def evaluate_rules(session: Session, expense: Expense) -> list[ChecklistRule]:
    """返回触发的规则（每种附件类型一条，取最严级别并合并提示）。

    多条规则合并时返回未入库的临时对象，调用方不应把它加入会话。
    """
    category_filter = ChecklistRule.category_id.is_(None)
    if expense.category_id is not None:
        category_filter = or_(category_filter, ChecklistRule.category_id == expense.category_id)
    rules = session.scalars(select(ChecklistRule).where(category_filter).order_by(ChecklistRule.id))
    policy = region_policy(session)
    merged: dict[str, ChecklistRule] = {}
    for rule in rules:
        if not condition_matches(rule.condition, expense, policy):
            continue
        kind = rule.attachment_kind
        merged[kind] = _merge(merged[kind], rule) if kind in merged else rule
    return list(merged.values())


def _attachment_kinds(session: Session, expense: Expense) -> set[str]:
    session.flush()
    query = select(Attachment.kind).where(Attachment.expense_id == expense.id)
    return set(session.scalars(query))


def _state_for(item: ChecklistItem, present_kinds: set[str]) -> str:
    if item.state == ChecklistState.NOT_NEEDED:
        return ChecklistState.NOT_NEEDED
    if item.attachment_kind in present_kinds:
        return ChecklistState.PRESENT
    return ChecklistState.MISSING


def compute_checklist(session: Session, expense: Expense) -> None:
    """同步清单项：保留“不需要”，新增触发项，删除不再触发且仍缺少的项。"""
    present_kinds = _attachment_kinds(session, expense)
    triggered = {rule.attachment_kind: rule for rule in evaluate_rules(session, expense)}
    existing: dict[str, ChecklistItem] = {}
    for item in list(expense.checklist_items):
        if item.attachment_kind in existing:
            expense.checklist_items.remove(item)  # 清理重复项
            continue
        existing[item.attachment_kind] = item
    for kind, rule in triggered.items():
        item = existing.get(kind)
        if item is None:
            item = ChecklistItem(attachment_kind=kind, state=ChecklistState.MISSING)
            expense.checklist_items.append(item)
        item.level = rule.level
        item.hint = rule.hint
    for item in list(expense.checklist_items):
        item.state = _state_for(item, present_kinds)
        if item.attachment_kind not in triggered and item.state == ChecklistState.MISSING:
            expense.checklist_items.remove(item)
    session.flush()


def required_missing_count(expense: Expense) -> int:
    return sum(
        1
        for item in expense.checklist_items
        if item.level == ChecklistLevel.REQUIRED and item.state == ChecklistState.MISSING
    )
