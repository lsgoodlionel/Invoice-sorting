"""账本描述 ledger.json（账本搬迁设计 2）：导出范围与来源，供合并导入的报告与批次改名使用。

ledger.json 与 manifest.json 同在 zip 根目录，只是说明性元数据：
不参与文件校验，读取时限制大小并逐字段校验类型，任何不符都视为包已损坏。
没有 ledger.json 的旧包按整账套包处理（`parse_ledger` 返回 None 由调用方决定）。
"""

import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from invoice_sorting.common.errors import AppError

LEDGER_NAME = "ledger.json"
LEDGER_KIND = "ledger"
LEDGER_MAX_BYTES = 64 * 1024
TEXT_MAX_CHARS = 100

MSG_LEDGER_BROKEN = "搬迁包的 ledger.json 无法解析或字段不正确，文件可能已损坏"


@dataclass(frozen=True)
class LedgerSource:
    """账本来源：部署形态、账套名称、导出人与程序版本。"""

    deployment: str = ""
    tenant: str = ""
    exported_by: str = ""
    app_version: str = ""


@dataclass(frozen=True)
class LedgerScope:
    """导出范围：记录（不含已删除）、附件、批次数量与记录的支出日期区间。"""

    records: int = 0
    attachments: int = 0
    batches: int = 0
    date_from: str = ""
    date_to: str = ""


@dataclass(frozen=True)
class LedgerInfo:
    source: LedgerSource
    scope: LedgerScope

    def to_dict(self) -> dict[str, object]:
        source, scope = self.source, self.scope
        return {
            "kind": LEDGER_KIND,
            "source": {
                "deployment": source.deployment,
                "tenant": source.tenant,
                "exported_by": source.exported_by,
                "app_version": source.app_version,
            },
            "scope": {
                "records": scope.records,
                "attachments": scope.attachments,
                "batches": scope.batches,
                "from": scope.date_from,
                "to": scope.date_to,
            },
        }

    def to_bytes(self) -> bytes:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")


def scope_of_snapshot(db_path: Path) -> LedgerScope:
    """直接读数据库快照统计范围，保证与包内数据一致（而不是读正在写入的业务库）。"""
    with closing(sqlite3.connect(db_path)) as conn:
        records, first, last = conn.execute(
            "select count(*), min(spent_on), max(spent_on) from expense where deleted = 0"
        ).fetchone()
        attachments = conn.execute("select count(*) from attachment").fetchone()[0]
        batches = conn.execute("select count(*) from batch").fetchone()[0]
    return LedgerScope(
        records=int(records or 0),
        attachments=int(attachments or 0),
        batches=int(batches or 0),
        date_from=str(first or ""),
        date_to=str(last or ""),
    )


def parse_ledger(raw: bytes) -> LedgerInfo:
    """解析并校验 ledger.json；字段缺失按空值处理，类型不符视为损坏。"""
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AppError(MSG_LEDGER_BROKEN) from error
    if not isinstance(payload, dict) or payload.get("kind") != LEDGER_KIND:
        raise AppError(MSG_LEDGER_BROKEN)
    return LedgerInfo(
        source=_parse_source(payload.get("source") or {}),
        scope=_parse_scope(payload.get("scope") or {}),
    )


def _parse_source(values: object) -> LedgerSource:
    if not isinstance(values, dict):
        raise AppError(MSG_LEDGER_BROKEN)
    return LedgerSource(
        deployment=_text(values.get("deployment")),
        tenant=_text(values.get("tenant")),
        exported_by=_text(values.get("exported_by")),
        app_version=_text(values.get("app_version")),
    )


def _parse_scope(values: object) -> LedgerScope:
    if not isinstance(values, dict):
        raise AppError(MSG_LEDGER_BROKEN)
    return LedgerScope(
        records=_count(values.get("records")),
        attachments=_count(values.get("attachments")),
        batches=_count(values.get("batches")),
        date_from=_text(values.get("from")),
        date_to=_text(values.get("to")),
    )


def _text(value: object) -> str:
    """说明性文本：只接受字符串，去掉控制字符并截断，避免把异常内容带进报告与批次名。"""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise AppError(MSG_LEDGER_BROKEN)
    cleaned = "".join(char for char in value if char.isprintable())
    return cleaned.strip()[:TEXT_MAX_CHARS]


def _count(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AppError(MSG_LEDGER_BROKEN)
    return value
