"""合并规划 · 记录与附件（账本搬迁设计 4.1）。

记录判重（命中即跳过，不改本地任何字段）：
1. 包内记录的某张发票号码已在本地某条记录上；
2. 金额 + 支出日期 + 商家相同，且附件集合有交集（按内容哈希或发票号）；
3. 两边都没有附件时，金额 + 日期 + 商家 + 摘要相同（设计之外的补充：
   否则无附件记录每导一次就多一条，破坏重复导入的幂等）。
附件已属于本地某条记录、但金额/日期/商家对不上时，记为**冲突**并跳过整条记录，交给人工核对。
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.common.money import cents_to_yuan
from invoice_sorting.db.models import Attachment, Expense, InvoiceData
from invoice_sorting.migration.manifest import FileEntry
from invoice_sorting.migration.merge_index import LocalIndex, compact, expense_key
from invoice_sorting.migration.report import (
    ACTION_ADDED,
    ACTION_CONFLICT,
    ACTION_FAILED,
    ACTION_SKIPPED,
    SECTION_ATTACHMENTS,
    SECTION_RECORDS,
    SectionBuilder,
    SectionReport,
)

STREAM_ROWS = 1000


@dataclass(frozen=True)
class PackageAttachment:
    id: int
    expense_id: int | None
    sha256: str
    invoice_no: str | None
    file_path: str
    original_name: str
    uploaded_by_id: int | None


@dataclass(frozen=True)
class RecordPlan:
    expenses: tuple[int, ...]  # 要新增的包内记录 id（升序）
    attachments: frozenset[int]  # 要新增的包内附件 id（含待归属）
    unassigned: tuple[int, ...]  # 其中的待归属附件
    actor_ids: frozenset[int]  # 新增记录与附件引用到的包内用户


@dataclass(frozen=True)
class _Verdict:
    action: str
    reason: str = ""


def load_package_attachments(pkg: Session) -> dict[int | None, list[PackageAttachment]]:
    """包内附件按所属记录分组（待归属的键为 None）；只取判重与落盘需要的字段。"""
    grouped: dict[int | None, list[PackageAttachment]] = {}
    query = (
        select(
            Attachment.id,
            Attachment.expense_id,
            Attachment.sha256,
            InvoiceData.invoice_no,
            Attachment.file_path,
            Attachment.original_name,
            Attachment.uploaded_by_id,
        )
        .outerjoin(InvoiceData, InvoiceData.attachment_id == Attachment.id)
        .order_by(Attachment.id)
    )
    for row in pkg.execute(query).yield_per(STREAM_ROWS):
        item = PackageAttachment(*row)
        grouped.setdefault(item.expense_id, []).append(item)
    return grouped


def expense_label(spent_on: date, merchant: str | None, amount_cents: int) -> str:
    return f"{spent_on:%Y-%m-%d} {merchant or '未填商家'} ¥{cents_to_yuan(amount_cents)}"


def attachment_verdict(
    item: PackageAttachment, index: LocalIndex, entries: Mapping[str, FileEntry]
) -> _Verdict:
    """单个附件：内容哈希或发票号已在本地则跳过；包里缺文件或校验和对不上记为失败。"""
    if item.sha256 in index.attachment_by_sha:
        return _Verdict(ACTION_SKIPPED, "文件内容与本地附件相同")
    if item.invoice_no and item.invoice_no in index.attachment_by_invoice:
        return _Verdict(ACTION_SKIPPED, f"发票号码 {item.invoice_no} 已存在")
    entry = entries.get(item.file_path)
    if entry is None:
        return _Verdict(ACTION_FAILED, "搬迁包里缺少该附件文件")
    if entry.sha256 != item.sha256:
        return _Verdict(ACTION_FAILED, "附件文件校验和与数据库记录不一致")
    return _Verdict(ACTION_ADDED)


def _match_expense(
    key: tuple, summary: str, items: list[PackageAttachment], index: LocalIndex, bare: dict
) -> _Verdict:
    for item in items:
        owner = index.attachment_by_invoice.get(item.invoice_no or "")
        if owner is not None and owner[1] is not None:
            return _Verdict(ACTION_SKIPPED, f"发票号码 {item.invoice_no} 已在本地记录 #{owner[1]}")
    owners = sorted(
        {index.attachment_by_sha[i.sha256][1] for i in items if i.sha256 in index.attachment_by_sha}
        - {None}
    )
    for local_id in owners:
        if index.expense_keys.get(local_id) == key:
            return _Verdict(
                ACTION_SKIPPED, f"与本地记录 #{local_id} 金额、日期、商家相同且附件重合"
            )
    if owners:
        reason = f"附件已属于本地记录 #{owners[0]}，但金额、日期或商家不一致，请人工核对"
        return _Verdict(ACTION_CONFLICT, reason)
    if not items:
        return _match_bare(key, summary, bare)
    return _Verdict(ACTION_ADDED)


def _match_bare(key: tuple, summary: str, bare: dict) -> _Verdict:
    """无附件记录：按键消费本地同样无附件的记录，两条相同的包内记录各自对应一条本地记录。"""
    candidates = bare.get((key, compact(summary)), ())
    if not candidates:
        return _Verdict(ACTION_ADDED)
    bare[(key, compact(summary))] = candidates[1:]
    return _Verdict(ACTION_SKIPPED, f"与本地无附件记录 #{candidates[0]} 金额、日期、商家、摘要相同")


class _RecordPlanner:
    """逐条记录判定并登记报告；只在规划期间存在。"""

    def __init__(self, index: LocalIndex, entries: Mapping[str, FileEntry]) -> None:
        self.index = index
        self.entries = entries
        self.bare = dict(index.bare_expenses)
        self.records = SectionBuilder()
        self.files = SectionBuilder()
        self.expenses: list[int] = []
        self.attachments: set[int] = set()
        self.actors: set[int] = set()

    def visit_expense(self, row: tuple, items: list[PackageAttachment]) -> None:
        expense_id, spent_on, cents, merchant, summary, deleted, created_by = row
        label = expense_label(spent_on, merchant, cents)
        if deleted:
            verdict = _Verdict(ACTION_SKIPPED, "来源账本中已删除，不导入")
        else:
            verdict = _match_expense(
                expense_key(cents, spent_on, merchant), summary, items, self.index, self.bare
            )
        self.records.add(verdict.action, label, verdict.reason)
        if verdict.action != ACTION_ADDED:
            self._skip_files(items, "所属记录未导入")
            return
        self.expenses.append(expense_id)
        self._remember(created_by)
        self.visit_files(items, f"（{label}）")

    def visit_files(self, items: Iterable[PackageAttachment], owner: str) -> None:
        for item in items:
            verdict = attachment_verdict(item, self.index, self.entries)
            self.files.add(verdict.action, f"{item.original_name}{owner}", verdict.reason)
            if verdict.action == ACTION_ADDED:
                self.attachments.add(item.id)
                self._remember(item.uploaded_by_id)

    def _skip_files(self, items: Iterable[PackageAttachment], reason: str) -> None:
        for item in items:
            self.files.add(ACTION_SKIPPED, item.original_name, reason)

    def _remember(self, user_id: int | None) -> None:
        if user_id is not None:
            self.actors.add(user_id)


def plan_records(
    pkg: Session, index: LocalIndex, entries: Mapping[str, FileEntry]
) -> tuple[RecordPlan, dict[str, SectionReport]]:
    grouped = load_package_attachments(pkg)
    planner = _RecordPlanner(index, entries)
    query = select(
        Expense.id,
        Expense.spent_on,
        Expense.amount_cents,
        Expense.merchant,
        Expense.summary,
        Expense.deleted,
        Expense.created_by_id,
    ).order_by(Expense.id)
    for row in pkg.execute(query).yield_per(STREAM_ROWS):
        planner.visit_expense(tuple(row), grouped.get(row[0], []))
    unassigned = grouped.get(None, [])
    planner.visit_files(unassigned, "（待归属）")
    plan = RecordPlan(
        expenses=tuple(planner.expenses),
        attachments=frozenset(planner.attachments),
        unassigned=tuple(item.id for item in unassigned if item.id in planner.attachments),
        actor_ids=frozenset(planner.actors),
    )
    reports = {SECTION_RECORDS: planner.records.build(), SECTION_ATTACHMENTS: planner.files.build()}
    return plan, reports
