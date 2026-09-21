"""合并规划 · 以导入包为准（勾选“同时导入系统设置”时）：分类外观、凭证规则、分类记忆。

- 同名分类：颜色、关键词、办理路径说明改为包内的值（名称、排序、归档状态不动）；
- 凭证规则按“分类 + 附件类型”对位：包内某位置的规则与本地同位规则不同时，
  本地该位置的规则整体替换为包内的；包里有、本地没有的位置照常新增；包里没有的位置不动；
- 分类记忆：同一商家/商品本地记为别的分类时，改记为包内的分类（本地独有的记忆保留）。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.db.models import Category, ChecklistRule
from invoice_sorting.migration.merge_index import (
    CategoryLook,
    LocalIndex,
    RulePosition,
    rule_content,
)
from invoice_sorting.migration.report import (
    ACTION_ADDED,
    ACTION_FAILED,
    ACTION_SKIPPED,
    ACTION_UPDATED,
    SectionBuilder,
    SectionReport,
)

GENERAL_RULE_LABEL = "通用"
FIELD_LABELS = (("color", "颜色"), ("keywords", "关键词"), ("route_hint", "办理路径说明"))
REASON_LOOK = "以导入包为准，更新{fields}"
REASON_RULES = "以导入包为准：本地同位规则 {old} 条替换为包内 {new} 条"
REASON_SAME_RULES = "本地同位规则与包内一致"


@dataclass(frozen=True)
class RuleOverride:
    new_rules: tuple[int, ...]  # 要新增的包内规则 id（含替换位置上的）
    replaced: tuple[int, ...]  # 要删除的本地规则 id


def look_of(category: Category) -> CategoryLook:
    words = category.keywords if isinstance(category.keywords, list) else []
    return CategoryLook(
        color=category.color or "",
        keywords=tuple(word for word in words if isinstance(word, str)),
        route_hint=category.route_hint or "",
    )


def look_change(incoming: CategoryLook, local: CategoryLook | None) -> str:
    """包内与本地不同的字段（中文名，顿号分隔）；完全一致时为空串。"""
    if local is None:
        return ""
    changed = [
        label for name, label in FIELD_LABELS if getattr(incoming, name) != getattr(local, name)
    ]
    return REASON_LOOK.format(fields="、".join(changed)) if changed else ""


def kind_label(kind: str) -> str:
    try:
        return AttachmentKind(kind).label
    except ValueError:
        return kind


def _valid_rules(
    pkg: Session, names: Mapping[int, str], report: SectionBuilder
) -> dict[tuple[int | None, str], list[ChecklistRule]]:
    """按包内位置分组；指向不存在的分类或条件格式不对的规则列为失败。"""
    grouped: dict[tuple[int | None, str], list[ChecklistRule]] = {}
    for rule in pkg.scalars(select(ChecklistRule).order_by(ChecklistRule.id)):
        owner = names.get(rule.category_id, GENERAL_RULE_LABEL) if rule.category_id else None
        label = f"凭证规则「{owner or GENERAL_RULE_LABEL} · {kind_label(rule.attachment_kind)}」"
        if rule.category_id is not None and rule.category_id not in names:
            report.add(ACTION_FAILED, label, "规则指向的分类在包内不存在，已忽略")
        elif not isinstance(rule.condition, dict):
            report.add(ACTION_FAILED, label, "规则条件格式不正确，已忽略")
        else:
            grouped.setdefault((rule.category_id, rule.attachment_kind), []).append(rule)
    return grouped


def _position_label(names: Mapping[int, str], category_id: int | None, kind: str) -> str:
    owner = names.get(category_id, GENERAL_RULE_LABEL) if category_id else GENERAL_RULE_LABEL
    return f"凭证规则「{owner} · {kind_label(kind)}」"


def plan_rule_override(
    pkg: Session, index: LocalIndex, categories: Mapping[int, int], names: Mapping[int, str]
) -> tuple[RuleOverride, SectionReport]:
    report = SectionBuilder()
    new: list[int] = []
    replaced: list[int] = []
    for (category_id, kind), rules in _valid_rules(pkg, names, report).items():
        label = _position_label(names, category_id, kind)
        local_category = categories.get(category_id) if category_id is not None else None
        is_new_category = category_id is not None and local_category is None
        position: RulePosition = (local_category, kind)
        local = () if is_new_category else index.rule_positions.get(position, ())
        ids = [rule.id for rule in rules]
        if not local:
            new.extend(ids)
            report.add(ACTION_ADDED, label, f"新增 {len(ids)} 条")
            continue
        incoming = sorted(rule_content(r.condition, r.level, r.hint) for r in rules)
        if incoming == sorted(content for _, content in local):
            report.add(ACTION_SKIPPED, label, REASON_SAME_RULES)
            continue
        new.extend(ids)
        replaced.extend(rule_id for rule_id, _ in local)
        report.add(ACTION_UPDATED, label, REASON_RULES.format(old=len(local), new=len(ids)))
    return RuleOverride(new_rules=tuple(new), replaced=tuple(replaced)), report.build()


def frozen_looks(updates: dict[int, CategoryLook]) -> Mapping[int, CategoryLook]:
    return MappingProxyType(dict(updates))
