"""合并规划 · 批次与资料包生成记录（账本搬迁设计 4.4）。

- 同一批次的判定：创建时间相同，且名称相同或为“名称（来自 …）”——即此前导入过的同一批次，
  重复导入时直接沿用，保证幂等；
- 新批次与本地同名时追加来源后缀，如“2026-09 第1批（来自 客户甲）”，仍冲突再加序号；
- 资料包 ZIP 不导入（可随时重新生成），只保留生成记录。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.db.models import Batch, ExportRecord
from invoice_sorting.migration.merge_index import LocalBatch, LocalIndex, naive
from invoice_sorting.migration.report import (
    ACTION_ADDED,
    ACTION_FAILED,
    ACTION_SKIPPED,
    SECTION_BATCHES,
    SECTION_EXPORTS,
    SectionBuilder,
    SectionReport,
)

BATCH_NAME_MAX = 100
SOURCE_OPEN = "（来自 "
SOURCE_CLOSE = "）"


@dataclass(frozen=True)
class BatchPlan:
    matched: Mapping[int, int]  # 包内批次 id → 本地同一批次 id
    new: Mapping[int, str]  # 包内批次 id → 导入后的名称
    new_exports: tuple[int, ...]
    actor_ids: frozenset[int]


def with_source(name: str, source: str, sequence: int = 1) -> str:
    """追加来源后缀；超长时截短原名称而不是后缀，保证能看出来源。"""
    tail = f"{SOURCE_OPEN}{source}{f' {sequence}' if sequence > 1 else ''}{SOURCE_CLOSE}"
    return f"{name[: max(BATCH_NAME_MAX - len(tail), 1)]}{tail}"


def _same_batch(local: LocalBatch, name: str, created_at: datetime | None) -> bool:
    if created_at is None or local.created_at != created_at:
        return False
    return local.name == name or local.name.startswith(f"{name}{SOURCE_OPEN}")


def _free_name(name: str, source: str, taken: set[str]) -> str:
    if name not in taken:
        return name
    sequence = 1
    while (candidate := with_source(name, source, sequence)) in taken:
        sequence += 1
    return candidate


def plan_batches(
    pkg: Session, index: LocalIndex, source: str
) -> tuple[BatchPlan, dict[str, SectionReport]]:
    matched: dict[int, int] = {}
    new: dict[int, str] = {}
    actors: set[int] = set()
    taken = {batch.name for batch in index.batches}
    report = SectionBuilder()
    for batch in pkg.scalars(select(Batch).order_by(Batch.id)):
        created_at = naive(batch.created_at)
        local = next((b for b in index.batches if _same_batch(b, batch.name, created_at)), None)
        if local is not None:
            matched[batch.id] = local.id
            report.add(ACTION_SKIPPED, f"批次「{batch.name}」", f"本地已有该批次「{local.name}」")
            continue
        name = _free_name(batch.name, source, taken)
        taken.add(name)
        new[batch.id] = name
        if batch.created_by_id is not None:
            actors.add(batch.created_by_id)
        reason = "" if name == batch.name else f"与本地批次重名，改名为「{name}」"
        report.add(ACTION_ADDED, f"批次「{batch.name}」", reason)
    exports, export_actors, export_report = _plan_exports(pkg, index, matched, new)
    plan = BatchPlan(
        matched=MappingProxyType(matched),
        new=MappingProxyType(new),
        new_exports=exports,
        actor_ids=frozenset(actors | export_actors),
    )
    return plan, {SECTION_BATCHES: report.build(), SECTION_EXPORTS: export_report}


def _plan_exports(
    pkg: Session, index: LocalIndex, matched: Mapping[int, int], new: Mapping[int, str]
) -> tuple[tuple[int, ...], set[int], SectionReport]:
    added: list[int] = []
    actors: set[int] = set()
    report = SectionBuilder()
    for record in pkg.scalars(select(ExportRecord).order_by(ExportRecord.id)):
        label = f"资料包生成记录（{record.created_at:%Y-%m-%d %H:%M}，{record.item_count} 条）"
        if record.batch_id in matched:
            if (matched[record.batch_id], record.sha256) in index.export_keys:
                report.add(ACTION_SKIPPED, label, "本地该批次已有相同的生成记录")
                continue
        elif record.batch_id not in new:
            report.add(ACTION_FAILED, label, "所属批次在包内不存在，已忽略")
            continue
        added.append(record.id)
        if record.created_by_id is not None:
            actors.add(record.created_by_id)
        report.add(ACTION_ADDED, label, "只导入生成记录，资料包文件不导入（可重新生成）")
    return tuple(added), actors, report.build()
