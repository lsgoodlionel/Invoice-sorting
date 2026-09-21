"""合并规划 · 目录类数据：分类、经费项目、凭证规则、分类记忆（账本搬迁设计 4.1）。

原则：按名称/内容合并，默认**冲突一律保留本地**，未采纳的包内内容进报告；
勾选“同时导入系统设置”（override=True）时，分类外观、凭证规则、分类记忆的冲突以导入包为准，
规则见 merge_plan_overrides。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.db.models import Category, ChecklistRule, ItemMemory, MerchantMemory, Project
from invoice_sorting.migration.merge_index import CategoryLook, LocalIndex, compact, rule_key
from invoice_sorting.migration.merge_plan_overrides import (
    RuleOverride,
    frozen_looks,
    kind_label,
    look_change,
    look_of,
    plan_rule_override,
)
from invoice_sorting.migration.report import (
    ACTION_ADDED,
    ACTION_CONFLICT,
    ACTION_FAILED,
    ACTION_SKIPPED,
    ACTION_UPDATED,
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
    # 以下仅在以导入包为准时非空
    category_updates: Mapping[int, CategoryLook] = MappingProxyType({})  # 本地分类 id → 新外观
    replaced_rules: tuple[int, ...] = ()  # 要删除的本地规则 id
    merchant_updates: tuple[str, ...] = ()  # 改记为包内分类的商家记忆
    item_updates: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Memories:
    new_merchants: tuple[str, ...]
    new_items: tuple[str, ...]
    merchant_updates: tuple[str, ...]
    item_updates: tuple[str, ...]


def plan_catalog(
    pkg: Session, index: LocalIndex, override: bool = False
) -> tuple[CatalogPlan, dict[str, SectionReport]]:
    categories, new_categories, names, looks, category_report = _plan_categories(
        pkg, index, override
    )
    projects, new_projects, project_report = _plan_projects(pkg, index)
    if override:
        rules, rule_report = plan_rule_override(pkg, index, categories, names)
    else:
        new_rules, rule_report = _plan_rules(pkg, index, categories, names)
        rules = RuleOverride(new_rules=new_rules, replaced=())
    memories, memory_report = _plan_memories(pkg, index, categories, names, override)
    plan = CatalogPlan(
        categories=MappingProxyType(categories),
        new_categories=new_categories,
        category_names=MappingProxyType(names),
        projects=MappingProxyType(projects),
        new_projects=new_projects,
        new_rules=rules.new_rules,
        new_merchant_memories=memories.new_merchants,
        new_item_memories=memories.new_items,
        category_updates=frozen_looks(looks),
        replaced_rules=rules.replaced,
        merchant_updates=memories.merchant_updates,
        item_updates=memories.item_updates,
    )
    reports = {
        SECTION_CATEGORIES: category_report,
        SECTION_PROJECTS: project_report,
        SECTION_RULES: rule_report,
        SECTION_MEMORIES: memory_report,
    }
    return plan, reports


def _plan_categories(
    pkg: Session, index: LocalIndex, override: bool
) -> tuple[dict[int, int], tuple[int, ...], dict[int, str], dict[int, CategoryLook], SectionReport]:
    matched: dict[int, int] = {}
    new: list[int] = []
    names: dict[int, str] = {}
    looks: dict[int, CategoryLook] = {}
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
        change = look_change(look_of(category), index.category_looks.get(local_id))
        if override and change:
            looks[local_id] = look_of(category)
            report.add(ACTION_UPDATED, label, change)
            continue
        extra = _extra_keywords(category.keywords, index.category_keywords.get(local_id))
        if extra:
            report.add(ACTION_CONFLICT, label, f"包内关键词 {extra} 未采纳（保留本地设置）")
        else:
            report.add(ACTION_SKIPPED, label, "本地已有同名分类")
    return matched, tuple(new), names, looks, report.build()


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


def _plan_rules(
    pkg: Session, index: LocalIndex, categories: Mapping[int, int], names: Mapping[int, str]
) -> tuple[tuple[int, ...], SectionReport]:
    new: list[int] = []
    report = SectionBuilder()
    for rule in pkg.scalars(select(ChecklistRule).order_by(ChecklistRule.id)):
        owner = names.get(rule.category_id, GENERAL_RULE_LABEL) if rule.category_id else None
        label = f"凭证规则「{owner or GENERAL_RULE_LABEL} · {kind_label(rule.attachment_kind)}」"
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


@dataclass(frozen=True)
class _MemoryContext:
    categories: Mapping[int, int]
    names: Mapping[int, str]
    report: SectionBuilder
    override: bool


def _plan_memories(
    pkg: Session,
    index: LocalIndex,
    categories: Mapping[int, int],
    names: Mapping[int, str],
    override: bool,
) -> tuple[_Memories, SectionReport]:
    ctx = _MemoryContext(categories, names, SectionBuilder(), override)
    merchants, merchant_updates = _plan_memory_table(
        pkg.execute(select(MerchantMemory.seller_name, MerchantMemory.category_id)).tuples(),
        index.merchant_memories,
        ctx,
        "商家记忆",
    )
    items, item_updates = _plan_memory_table(
        pkg.execute(select(ItemMemory.item_name, ItemMemory.category_id)).tuples(),
        index.item_memories,
        ctx,
        "商品记忆",
    )
    memories = _Memories(merchants, items, merchant_updates, item_updates)
    return memories, ctx.report.build()


def _plan_memory_table(
    rows,  # noqa: ANN001 - (键, 分类 id) 的查询结果
    local: Mapping[str, int],
    ctx: _MemoryContext,
    what: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    new: list[str] = []
    updates: list[str] = []
    names, categories, report = ctx.names, ctx.categories, ctx.report
    for key, category_id in sorted(rows):
        label = f"{what}「{key}」→ {names.get(category_id, '未知分类')}"
        if category_id not in names:
            report.add(ACTION_FAILED, label, "记忆指向的分类在包内不存在，已忽略")
        elif key not in local:
            new.append(key)
            report.add(ACTION_ADDED, label)
        elif local[key] == categories.get(category_id):
            report.add(ACTION_SKIPPED, label, "本地已有相同记忆")
        elif ctx.override:
            updates.append(key)
            report.add(ACTION_UPDATED, label, "以导入包为准，改记为包内的分类")
        else:
            report.add(ACTION_CONFLICT, label, "本地已记为其他分类，保留本地")
    return tuple(new), tuple(updates)
