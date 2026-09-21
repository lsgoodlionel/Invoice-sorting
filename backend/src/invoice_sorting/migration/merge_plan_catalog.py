"""合并规划 · 目录类数据：分类、经费项目、凭证规则、分类记忆（账本搬迁设计 4.1）。

原则：按名称/内容合并，**冲突一律保留本地**，未采纳的包内内容进报告；本地设置一概不改。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.db.models import Category, ChecklistRule, ItemMemory, MerchantMemory, Project
from invoice_sorting.migration.merge_index import LocalIndex, compact, rule_key
from invoice_sorting.migration.report import (
    ACTION_ADDED,
    ACTION_CONFLICT,
    ACTION_FAILED,
    ACTION_SKIPPED,
    SECTION_CATEGORIES,
    SECTION_MEMORIES,
    SECTION_PROJECTS,
    SECTION_RULES,
    SectionBuilder,
    SectionReport,
)

KEYWORDS_SHOWN = 10
GENERAL_RULE_LABEL = "通用"


@dataclass(frozen=True)
class CatalogPlan:
    categories: Mapping[int, int]  # 包内 id → 本地同名分类 id
    new_categories: tuple[int, ...]
    category_names: Mapping[int, str]  # 包内 id → 名称（报告用）
    projects: Mapping[int, int]
    new_projects: tuple[int, ...]
    new_rules: tuple[int, ...]
    new_merchant_memories: tuple[str, ...]
    new_item_memories: tuple[str, ...]


def plan_catalog(pkg: Session, index: LocalIndex) -> tuple[CatalogPlan, dict[str, SectionReport]]:
    categories, new_categories, names, category_report = _plan_categories(pkg, index)
    projects, new_projects, project_report = _plan_projects(pkg, index)
    new_rules, rule_report = _plan_rules(pkg, index, categories, names)
    merchants, items, memory_report = _plan_memories(pkg, index, categories, names)
    plan = CatalogPlan(
        categories=MappingProxyType(categories),
        new_categories=new_categories,
        category_names=MappingProxyType(names),
        projects=MappingProxyType(projects),
        new_projects=new_projects,
        new_rules=new_rules,
        new_merchant_memories=merchants,
        new_item_memories=items,
    )
    reports = {
        SECTION_CATEGORIES: category_report,
        SECTION_PROJECTS: project_report,
        SECTION_RULES: rule_report,
        SECTION_MEMORIES: memory_report,
    }
    return plan, reports


def _plan_categories(
    pkg: Session, index: LocalIndex
) -> tuple[dict[int, int], tuple[int, ...], dict[int, str], SectionReport]:
    matched: dict[int, int] = {}
    new: list[int] = []
    names: dict[int, str] = {}
    report = SectionBuilder()
    for category in pkg.scalars(select(Category).order_by(Category.id)):
        names[category.id] = category.name
        local_id = index.categories_by_name.get(compact(category.name))
        label = f"分类「{category.name}」"
        if local_id is None:
            new.append(category.id)
            report.add(ACTION_ADDED, label)
            continue
        matched[category.id] = local_id
        extra = _extra_keywords(category.keywords, index.category_keywords.get(local_id))
        if extra:
            report.add(ACTION_CONFLICT, label, f"包内关键词 {extra} 未采纳（保留本地设置）")
        else:
            report.add(ACTION_SKIPPED, label, "本地已有同名分类")
    return matched, tuple(new), names, report.build()


def _extra_keywords(package_words: object, local_words: frozenset[str] | None) -> str:
    words = (
        [w for w in package_words if isinstance(w, str)] if isinstance(package_words, list) else []
    )
    extra = [word for word in words if word not in (local_words or frozenset())]
    shown = "、".join(extra[:KEYWORDS_SHOWN])
    return f"{shown} 等 {len(extra)} 个" if len(extra) > KEYWORDS_SHOWN else shown


def _plan_projects(
    pkg: Session, index: LocalIndex
) -> tuple[dict[int, int], tuple[int, ...], SectionReport]:
    matched: dict[int, int] = {}
    new: list[int] = []
    report = SectionBuilder()
    for project in pkg.scalars(select(Project).order_by(Project.id)):
        local_id = index.projects_by_name.get(compact(project.name))
        label = f"经费项目「{project.name}」"
        if local_id is None:
            new.append(project.id)
            report.add(ACTION_ADDED, label)
        else:
            matched[project.id] = local_id
            report.add(ACTION_SKIPPED, label, "本地已有同名项目")
    return matched, tuple(new), report.build()


def _kind_label(kind: str) -> str:
    try:
        return AttachmentKind(kind).label
    except ValueError:
        return kind


def _plan_rules(
    pkg: Session, index: LocalIndex, categories: Mapping[int, int], names: Mapping[int, str]
) -> tuple[tuple[int, ...], SectionReport]:
    new: list[int] = []
    report = SectionBuilder()
    for rule in pkg.scalars(select(ChecklistRule).order_by(ChecklistRule.id)):
        owner = names.get(rule.category_id, GENERAL_RULE_LABEL) if rule.category_id else None
        label = f"凭证规则「{owner or GENERAL_RULE_LABEL} · {_kind_label(rule.attachment_kind)}」"
        if rule.category_id is not None and rule.category_id not in names:
            report.add(ACTION_FAILED, label, "规则指向的分类在包内不存在，已忽略")
            continue
        if not isinstance(rule.condition, dict):
            report.add(ACTION_FAILED, label, "规则条件格式不正确，已忽略")
            continue
        local_category = categories.get(rule.category_id) if rule.category_id else None
        is_new_category = rule.category_id is not None and local_category is None
        found = (
            None
            if is_new_category
            else index.rules.get(rule_key(local_category, rule.attachment_kind, rule.condition))
        )
        if found is None:
            new.append(rule.id)
            report.add(ACTION_ADDED, label)
        elif found == (rule.level, rule.hint):
            report.add(ACTION_SKIPPED, label, "本地已有相同规则")
        else:
            report.add(ACTION_CONFLICT, label, "本地同条件规则的要求或提示不同，保留本地")
    return tuple(new), report.build()


def _plan_memories(
    pkg: Session, index: LocalIndex, categories: Mapping[int, int], names: Mapping[int, str]
) -> tuple[tuple[str, ...], tuple[str, ...], SectionReport]:
    report = SectionBuilder()
    merchants = _plan_memory_table(
        pkg.execute(select(MerchantMemory.seller_name, MerchantMemory.category_id)).tuples(),
        index.merchant_memories,
        categories,
        names,
        report,
        "商家记忆",
    )
    items = _plan_memory_table(
        pkg.execute(select(ItemMemory.item_name, ItemMemory.category_id)).tuples(),
        index.item_memories,
        categories,
        names,
        report,
        "商品记忆",
    )
    return merchants, items, report.build()


def _plan_memory_table(  # noqa: PLR0913 - 两张记忆表共用同一套判定
    rows,  # noqa: ANN001 - (键, 分类 id) 的查询结果
    local: Mapping[str, int],
    categories: Mapping[int, int],
    names: Mapping[int, str],
    report: SectionBuilder,
    what: str,
) -> tuple[str, ...]:
    new: list[str] = []
    for key, category_id in sorted(rows):
        label = f"{what}「{key}」→ {names.get(category_id, '未知分类')}"
        if category_id not in names:
            report.add(ACTION_FAILED, label, "记忆指向的分类在包内不存在，已忽略")
        elif key not in local:
            new.append(key)
            report.add(ACTION_ADDED, label)
        elif local[key] == categories.get(category_id):
            report.add(ACTION_SKIPPED, label, "本地已有相同记忆")
        else:
            report.add(ACTION_CONFLICT, label, "本地已记为其他分类，保留本地")
    return tuple(new)
