"""合并规划：只读包内库与目标账本，得出“新增什么、跳过什么、冲突在哪”。

预览直接返回规划报告；真正导入按同一份规划执行，因此预览与结果口径一致。
人（账本搬迁设计 4.3）：只处理**新增行引用到的**上传人与操作人——按用户名匹配本地账号，
匹配不到的在执行时创建停用的占位账号。
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import batched
from types import MappingProxyType

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.db.models import StatusEvent, User
from invoice_sorting.migration.merge_index import LocalIndex, load_local_index
from invoice_sorting.migration.merge_plan_batches import BatchPlan, plan_batches
from invoice_sorting.migration.merge_plan_catalog import CatalogPlan, plan_catalog
from invoice_sorting.migration.merge_plan_records import RecordPlan, plan_records
from invoice_sorting.migration.package import PackageInfo
from invoice_sorting.migration.report import (
    ACTION_ADDED,
    ACTION_SKIPPED,
    SECTION_USERS,
    SectionBuilder,
    SectionReport,
    freeze_sections,
)

IN_CLAUSE_CHUNK = 500


@dataclass(frozen=True)
class Placeholder:
    """匹配不到本地账号的包内用户：执行时创建停用占位账号，保留姓名。"""

    package_id: int
    username: str
    display_name: str


@dataclass(frozen=True)
class UserPlan:
    matched: Mapping[int, int]  # 包内用户 id → 本地用户 id
    placeholders: tuple[Placeholder, ...]


@dataclass(frozen=True)
class MergePlan:
    catalog: CatalogPlan
    batches: BatchPlan
    records: RecordPlan
    users: UserPlan
    sections: Mapping[str, SectionReport]

    @property
    def is_empty(self) -> bool:
        """没有任何需要写入的内容（例如重复导入同一个包）。"""
        return sum(section.added for section in self.sections.values()) == 0


def build_plan(pkg: Session, db: Session, info: PackageInfo) -> MergePlan:
    index = load_local_index(db)
    catalog, sections = plan_catalog(pkg, index)
    batches, batch_sections = plan_batches(pkg, index, info.source_label)
    records, record_sections = plan_records(pkg, index, info.entries_by_path())
    actors = records.actor_ids | batches.actor_ids | _event_actors(pkg, records.expenses)
    users, user_report = plan_users(pkg, index, actors)
    all_sections = {**sections, **batch_sections, **record_sections, SECTION_USERS: user_report}
    return MergePlan(
        catalog=catalog,
        batches=batches,
        records=records,
        users=users,
        sections=freeze_sections(all_sections),
    )


def _event_actors(pkg: Session, expense_ids: Iterable[int]) -> frozenset[int]:
    """新增记录的时间线操作人（分块查询，避免 IN 子句过长）。"""
    found: set[int] = set()
    for chunk in batched(expense_ids, IN_CLAUSE_CHUNK):
        query = select(StatusEvent.actor_id).where(
            StatusEvent.expense_id.in_(chunk), StatusEvent.actor_id.is_not(None)
        )
        found.update(pkg.scalars(query))
    return frozenset(found)


def plan_users(
    pkg: Session, index: LocalIndex, actor_ids: frozenset[int]
) -> tuple[UserPlan, SectionReport]:
    matched: dict[int, int] = {}
    placeholders: list[Placeholder] = []
    report = SectionBuilder()
    rows: list[tuple[int, str, str]] = []
    for chunk in batched(sorted(actor_ids), IN_CLAUSE_CHUNK):
        query = select(User.id, User.username, User.display_name).where(User.id.in_(chunk))
        rows.extend(pkg.execute(query).tuples())
    for user_id, username, display_name in sorted(rows):
        name = (username or "").strip().lower()
        label = f"{display_name or name}（{name}）"
        local_id = index.users_by_name.get(name)
        if local_id is not None:
            matched[user_id] = local_id
            report.add(ACTION_SKIPPED, label, "按用户名匹配到本地账号")
            continue
        placeholders.append(Placeholder(user_id, name, display_name or name))
        report.add(ACTION_ADDED, label, "本地没有该用户，创建停用的占位账号（不能登录）")
    return UserPlan(matched=MappingProxyType(matched), placeholders=tuple(placeholders)), (
        report.build()
    )
