"""合并导入的本地索引：一次性读出目标账本里判重需要的键（只读，不持有 ORM 对象）。

判重规则（账本搬迁设计 4.1）：
- 附件按**文件内容哈希**判重。设计里写作 file_key，但本程序的 `attachment.file_key`
  是“文件名键”（同一笔支出的分组线索，可为空、不唯一），内容哈希在 `attachment.sha256`
  （唯一约束），因此以 sha256 为准；
- 发票按发票号码；
- 记录按“同发票号”或“金额 + 支出日期 + 商家且附件有交集”。
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.db.models import (
    Attachment,
    Batch,
    Category,
    ChecklistRule,
    Expense,
    ExportRecord,
    InvoiceData,
    ItemMemory,
    MerchantMemory,
    Project,
    User,
)

ExpenseKey = tuple[int, date, str]
RuleKey = tuple[int | None, str, str]
Owner = tuple[int, int | None]  # (附件 id, 所属记录 id；待归属为 None)


def compact(text: str | None) -> str:
    """名称比较用：去掉全部空白（“去空格”）。"""
    return "".join((text or "").split())


def expense_key(amount_cents: int, spent_on: date, merchant: str | None) -> ExpenseKey:
    return (int(amount_cents), spent_on, compact(merchant))


def rule_key(category_id: int | None, kind: str, condition: object) -> RuleKey:
    """规则内容键：分类 + 附件类型 + 条件（条件按键排序序列化，保证比较稳定）。"""
    canonical = json.dumps(condition or {}, ensure_ascii=False, sort_keys=True)
    return (category_id, kind, canonical)


def naive(moment: datetime | None) -> datetime | None:
    """SQLite 不保存时区，比较时间前统一去掉时区信息。"""
    return moment.replace(tzinfo=None) if moment is not None else None


@dataclass(frozen=True)
class LocalBatch:
    id: int
    name: str
    created_at: datetime | None


@dataclass(frozen=True)
class LocalIndex:
    """目标账本的判重索引；构造后只读。"""

    attachment_by_sha: Mapping[str, Owner]
    attachment_by_invoice: Mapping[str, Owner]
    expense_keys: Mapping[int, ExpenseKey]
    bare_expenses: Mapping[tuple[ExpenseKey, str], tuple[int, ...]]  # 无附件记录（含摘要）
    users_by_name: Mapping[str, int]
    categories_by_name: Mapping[str, int]
    category_keywords: Mapping[int, frozenset[str]]
    projects_by_name: Mapping[str, int]
    rules: Mapping[RuleKey, tuple[str, str]]  # → (level, hint)
    merchant_memories: Mapping[str, int]
    item_memories: Mapping[str, int]
    batches: tuple[LocalBatch, ...]
    export_keys: frozenset[tuple[int, str]]  # (批次 id, 资料包 sha256)


def load_local_index(db: Session) -> LocalIndex:
    by_sha, by_invoice = _attachment_owners(db)
    keys, bare = _expense_keys(db, {owner for _, owner in by_sha.values() if owner})
    categories = list(db.execute(select(Category.id, Category.name, Category.keywords)))
    return LocalIndex(
        attachment_by_sha=by_sha,
        attachment_by_invoice=by_invoice,
        expense_keys=keys,
        bare_expenses=bare,
        users_by_name={
            name.lower(): uid for uid, name in db.execute(select(User.id, User.username))
        },
        categories_by_name=_first_by_name((cid, name) for cid, name, _ in categories),
        category_keywords={cid: frozenset(_keywords(words)) for cid, _, words in categories},
        projects_by_name=_first_by_name(db.execute(select(Project.id, Project.name))),
        rules=_rules(db),
        merchant_memories=_pairs(db, MerchantMemory.seller_name, MerchantMemory.category_id),
        item_memories=_pairs(db, ItemMemory.item_name, ItemMemory.category_id),
        batches=tuple(
            LocalBatch(id=bid, name=name, created_at=naive(created))
            for bid, name, created in db.execute(select(Batch.id, Batch.name, Batch.created_at))
        ),
        export_keys=frozenset(
            db.execute(select(ExportRecord.batch_id, ExportRecord.sha256)).tuples()
        ),
    )


def _pairs(db: Session, key, value) -> dict:  # noqa: ANN001 - 两个映射列
    """两列查询转字典（Result 自带 keys()，不能直接交给 dict()）。"""
    return {row_key: row_value for row_key, row_value in db.execute(select(key, value))}


def _attachment_owners(db: Session) -> tuple[dict[str, Owner], dict[str, Owner]]:
    rows = db.execute(
        select(
            Attachment.id, Attachment.expense_id, Attachment.sha256, InvoiceData.invoice_no
        ).outerjoin(InvoiceData, InvoiceData.attachment_id == Attachment.id)
    )
    by_sha: dict[str, Owner] = {}
    by_invoice: dict[str, Owner] = {}
    for attachment_id, expense_id, sha, invoice_no in rows:
        by_sha[sha] = (attachment_id, expense_id)
        if invoice_no:
            by_invoice[invoice_no] = (attachment_id, expense_id)
    return by_sha, by_invoice


def _expense_keys(
    db: Session, with_files: set[int]
) -> tuple[dict[int, ExpenseKey], dict[tuple[ExpenseKey, str], tuple[int, ...]]]:
    """全部记录（含已删除，避免把本地删掉的又导回来）的判重键；无附件记录另建索引。"""
    keys: dict[int, ExpenseKey] = {}
    bare: dict[tuple[ExpenseKey, str], tuple[int, ...]] = {}
    rows = db.execute(
        select(
            Expense.id, Expense.amount_cents, Expense.spent_on, Expense.merchant, Expense.summary
        )
    )
    for expense_id, cents, spent_on, merchant, summary in rows:
        key = expense_key(cents, spent_on, merchant)
        keys[expense_id] = key
        if expense_id not in with_files:
            bare_key = (key, compact(summary))
            bare[bare_key] = (*bare.get(bare_key, ()), expense_id)
    return keys, bare


def _first_by_name(rows) -> dict[str, int]:  # noqa: ANN001 - (id, name) 的可迭代结果
    """同名项取 id 最小的一条（与界面默认排序一致）。"""
    found: dict[str, int] = {}
    for row_id, name in sorted(rows, key=lambda row: row[0]):
        found.setdefault(compact(name), row_id)
    return found


def _keywords(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    return [word for word in values if isinstance(word, str)]


def _rules(db: Session) -> dict[RuleKey, tuple[str, str]]:
    rows = db.execute(
        select(
            ChecklistRule.category_id,
            ChecklistRule.attachment_kind,
            ChecklistRule.condition,
            ChecklistRule.level,
            ChecklistRule.hint,
        )
    )
    return {rule_key(cid, kind, cond): (level, hint) for cid, kind, cond, level, hint in rows}
