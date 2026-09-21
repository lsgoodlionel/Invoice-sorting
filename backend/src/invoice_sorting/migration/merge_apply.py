"""合并执行 · 目录、人、批次与生成记录：按规划新增，**重新分配全部主键**并改写外键。

包内 id 只用作查找与映射表的键，任何写入本地的行都由本地数据库分配新 id（账本搬迁设计 4.2）。
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from invoice_sorting.attachments.storage import safe_component
from invoice_sorting.config import PACKAGES_DIRNAME
from invoice_sorting.db.models import (
    Batch,
    Category,
    ChecklistRule,
    ExportRecord,
    ItemMemory,
    MerchantMemory,
    Project,
)
from invoice_sorting.migration.merge_plan import UserPlan
from invoice_sorting.migration.merge_plan_batches import BatchPlan
from invoice_sorting.migration.merge_plan_catalog import CatalogPlan
from invoice_sorting.migration.placeholders import CreatedPlaceholder, create_placeholders

IMPORTED_EXPORTS_DIRNAME = "已导入_未含文件"
EXPORT_TOKEN_CHARS = 8
FALLBACK_EXPORT_NAME = "资料包.zip"


def copy_columns(row: object, exclude: frozenset[str]) -> dict[str, Any]:
    """按模型列复制字段值（不含主键与需要改写的外键）；只复制值，不共享对象。"""
    mapper = inspect(type(row))
    return {
        attr.key: getattr(row, attr.key) for attr in mapper.column_attrs if attr.key not in exclude
    }


def choice(value: object, allowed: type[StrEnum], default: str) -> str:
    """枚举型文本字段：包内值不在本程序认识的范围内时回退到默认值。"""
    text = str(value or "")
    return text if text in {member.value for member in allowed} else default


def string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


@dataclass(frozen=True)
class IdMaps:
    """包内 id → 本地 id。查不到（包内为空或指向不存在的行）一律视为 None。"""

    users: Mapping[int, int]
    categories: Mapping[int, int]
    projects: Mapping[int, int]
    batches: Mapping[int, int]

    @staticmethod
    def _get(mapping: Mapping[int, int], key: int | None) -> int | None:
        return mapping.get(key) if key is not None else None

    def user(self, key: int | None) -> int | None:
        return self._get(self.users, key)

    def category(self, key: int | None) -> int | None:
        return self._get(self.categories, key)

    def project(self, key: int | None) -> int | None:
        return self._get(self.projects, key)

    def batch(self, key: int | None) -> int | None:
        return self._get(self.batches, key)


def apply_users(
    control: Session, db: Session, tenant_id: int, plan: UserPlan
) -> tuple[Mapping[int, int], tuple[CreatedPlaceholder, ...]]:
    created = create_placeholders(control, db, tenant_id, plan.placeholders)
    mapping = {**plan.matched, **{item.package_id: item.account_id for item in created}}
    return MappingProxyType(mapping), created


def apply_catalog(
    db: Session, pkg: Session, plan: CatalogPlan
) -> tuple[Mapping[int, int], Mapping[int, int]]:
    """新增分类与项目并返回完整映射；再按映射写入规则与分类记忆（以包为准时先改写本地）。"""
    _apply_category_looks(db, plan)
    categories = dict(plan.categories)
    for package_id in plan.new_categories:
        row = pkg.get(Category, package_id)
        values = copy_columns(row, frozenset({"id", "keywords"}))
        created = Category(**values, keywords=string_list(row.keywords))
        db.add(created)
        db.flush()
        categories[package_id] = created.id
    projects = dict(plan.projects)
    for package_id in plan.new_projects:
        created = Project(**copy_columns(pkg.get(Project, package_id), frozenset({"id"})))
        db.add(created)
        db.flush()
        projects[package_id] = created.id
    _apply_rules(db, pkg, plan, categories)
    _apply_memories(db, pkg, plan, categories)
    db.flush()
    return MappingProxyType(categories), MappingProxyType(projects)


def _apply_category_looks(db: Session, plan: CatalogPlan) -> None:
    for local_id, look in plan.category_updates.items():
        row = db.get(Category, local_id)
        row.color = look.color
        row.keywords = list(look.keywords)
        row.route_hint = look.route_hint
    db.flush()


def _apply_rules(
    db: Session, pkg: Session, plan: CatalogPlan, categories: Mapping[int, int]
) -> None:
    for local_id in plan.replaced_rules:
        db.delete(db.get(ChecklistRule, local_id))
    db.flush()
    for package_id in plan.new_rules:
        row = pkg.get(ChecklistRule, package_id)
        values = copy_columns(row, frozenset({"id", "category_id", "condition"}))
        category_id = categories.get(row.category_id) if row.category_id is not None else None
        db.add(ChecklistRule(**values, category_id=category_id, condition=dict(row.condition)))


def _apply_memories(
    db: Session, pkg: Session, plan: CatalogPlan, categories: Mapping[int, int]
) -> None:
    for key in plan.new_merchant_memories:
        row = pkg.get(MerchantMemory, key)
        db.add(
            MerchantMemory(
                seller_name=key, category_id=categories[row.category_id], updated_at=row.updated_at
            )
        )
    for key in plan.new_item_memories:
        row = pkg.get(ItemMemory, key)
        db.add(
            ItemMemory(
                item_name=key, category_id=categories[row.category_id], updated_at=row.updated_at
            )
        )
    _apply_memory_updates(db, pkg, plan, categories)


def _apply_memory_updates(
    db: Session, pkg: Session, plan: CatalogPlan, categories: Mapping[int, int]
) -> None:
    """以包为准：本地已有的同名记忆改指包内分类（对应到本地后的 id）。"""
    for model, keys in ((MerchantMemory, plan.merchant_updates), (ItemMemory, plan.item_updates)):
        for key in keys:
            db.get(model, key).category_id = categories[pkg.get(model, key).category_id]


def apply_batches(
    db: Session,
    pkg: Session,
    plan: BatchPlan,
    users: Mapping[int, int],
    projects: Mapping[int, int],
) -> Mapping[int, int]:
    maps = IdMaps(users=users, categories={}, projects=projects, batches={})
    batches = dict(plan.matched)
    for package_id, name in plan.new.items():
        row = pkg.get(Batch, package_id)
        values = copy_columns(row, frozenset({"id", "name", "project_id", "created_by_id"}))
        created = Batch(
            **values,
            name=name,
            project_id=maps.project(row.project_id),
            created_by_id=maps.user(row.created_by_id),
        )
        db.add(created)
        db.flush()
        batches[package_id] = created.id
    return MappingProxyType(batches)


def imported_export_path(original: str) -> str:
    """生成记录的文件路径：资料包没有随包导入，指向一个不存在且不会与本地冲突的位置。

    不沿用包内路径——那可能恰好指向本地另一个批次的资料包，下载或删除时会误伤本地文件。
    """
    name = safe_component(PurePosixPath(original or "").name) or FALLBACK_EXPORT_NAME
    token = uuid.uuid4().hex[:EXPORT_TOKEN_CHARS]
    return f"{PACKAGES_DIRNAME}/{IMPORTED_EXPORTS_DIRNAME}/{token}_{name}"


def apply_exports(db: Session, pkg: Session, plan: BatchPlan, maps: IdMaps) -> None:
    exclude = frozenset({"id", "batch_id", "created_by_id", "file_path"})
    for package_id in plan.new_exports:
        row = pkg.get(ExportRecord, package_id)
        db.add(
            ExportRecord(
                **copy_columns(row, exclude),
                batch_id=maps.batch(row.batch_id),
                created_by_id=maps.user(row.created_by_id),
                file_path=imported_export_path(row.file_path),
            )
        )
    db.flush()
