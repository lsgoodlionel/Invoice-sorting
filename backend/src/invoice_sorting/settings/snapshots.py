"""数据库快照：列出与下载备份目录里本账本的数据库副本。

只认两类文件名：手动快照 `invoice_*.db` 与升级前自动备份 `upgrade_*.db`。
控制库的备份（`control_upgrade_*.db`）含所有账套的账号与密码哈希，**绝不列出、绝不允许下载**。
文件名按白名单正则校验并确认落在备份目录内，防止路径穿越。
"""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from invoice_sorting.common.errors import NotFoundError
from invoice_sorting.config import Settings
from invoice_sorting.settings.service import BACKUP_PREFIX

UPGRADE_PREFIX = "upgrade_"
KIND_MANUAL = "manual"
KIND_UPGRADE = "upgrade"
SNAPSHOT_NAME = re.compile(rf"^(?:{BACKUP_PREFIX}|{UPGRADE_PREFIX})[0-9_]+\.db$")
WHAT_SNAPSHOT = "数据库快照"
LOCAL_TZ = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class Snapshot:
    name: str
    kind: str
    size: int
    created_at: datetime

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "kind": self.kind,
            "size": self.size,
            "created_at": self.created_at.isoformat(),
        }


def _kind_of(name: str) -> str:
    return KIND_UPGRADE if name.startswith(UPGRADE_PREFIX) else KIND_MANUAL


def _snapshot(path: Path) -> Snapshot:
    stat = path.stat()
    return Snapshot(
        name=path.name,
        kind=_kind_of(path.name),
        size=stat.st_size,
        created_at=datetime.fromtimestamp(stat.st_mtime, LOCAL_TZ),
    )


def list_snapshots(settings: Settings) -> list[Snapshot]:
    """最新的在前；备份目录不存在时为空。"""
    directory = settings.backup_dir
    if not directory.is_dir():
        return []
    files = [
        path for path in directory.iterdir() if path.is_file() and SNAPSHOT_NAME.match(path.name)
    ]
    return sorted((_snapshot(path) for path in files), key=lambda s: s.created_at, reverse=True)


def resolve_snapshot(settings: Settings, name: str) -> Path:
    """校验文件名并返回路径；不合法、不存在或越出备份目录一律按“不存在”处理。"""
    if not SNAPSHOT_NAME.match(name):
        raise NotFoundError(WHAT_SNAPSHOT)
    directory = settings.backup_dir.resolve()
    path = (directory / name).resolve()
    if path.parent != directory or not path.is_file():
        raise NotFoundError(WHAT_SNAPSHOT)
    return path
