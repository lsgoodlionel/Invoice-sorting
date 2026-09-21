"""账本备份包的存放、列表与下载（本地部署与 SaaS 同一套）。

备份即导出：账套自助导出的完整包（数据库 + 附件 + 系统设置）落在**该账套自己的**
`备份/账本备份/` 下（单账套就是数据目录下的 `备份/账本备份/`），按账套各自保留最近
KEEP_LEDGER_BACKUPS 份；SaaS 下各账套的数据目录互不相交，天然隔离。

每个包旁边有一个同名侧车文件 `<包名>.json`，记录导出选项与导出人等元数据；
侧车缺失或损坏时列表照常显示（元数据按缺省值）。文件名按白名单正则校验，
并确认解析后的路径就在本账套备份目录内，防止路径穿越。
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from invoice_sorting.common.backup_files import matching_files, prune_matching, resolve_in_dir
from invoice_sorting.config import Settings
from invoice_sorting.db.models import TZ

logger = logging.getLogger(__name__)

LEDGER_BACKUPS_DIRNAME = "账本备份"
KEEP_LEDGER_BACKUPS = 10
SIDECAR_SUFFIX = ".json"
# 与 export.export_filename 生成的名字一一对应：账套_<slug>_<年月日>_<时分秒>[_<任务号前 8 位>].zip
PACKAGE_NAME = re.compile(r"^账套_[a-z0-9][a-z0-9-]{0,49}_\d{8}_\d{6}(?:_[0-9a-f]{8})?\.zip$")
WHAT_PACKAGE = "账本备份包"


@dataclass(frozen=True)
class PackageMeta:
    """侧车里的元数据（只放展示用信息，不放任何路径或密钥）。"""

    include_packages: bool = True
    file_count: int = 0
    exported_by: str = ""

    def to_json(self) -> str:
        return json.dumps(self.__dict__, ensure_ascii=False)


@dataclass(frozen=True)
class LedgerBackup:
    name: str
    size: int
    created_at: datetime
    meta: PackageMeta

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "size": self.size,
            "created_at": self.created_at.isoformat(),
            "include_packages": self.meta.include_packages,
            "file_count": self.meta.file_count,
            "exported_by": self.meta.exported_by,
        }


def ledger_backups_dir(tenant_settings: Settings) -> Path:
    """某账套的账本备份目录；参数须是该账套自己的配置（base.for_tenant(slug)）。"""
    return tenant_settings.backup_dir / LEDGER_BACKUPS_DIRNAME


def sidecar_of(package: Path) -> Path:
    return package.with_name(package.name + SIDECAR_SUFFIX)


def write_meta(package: Path, meta: PackageMeta) -> None:
    """写侧车；失败只记日志——包本身已经完整可用。"""
    try:
        sidecar_of(package).write_text(meta.to_json(), encoding="utf-8")
    except OSError:
        logger.warning("写入备份包元数据失败：%s", package.name)


def read_meta(package: Path) -> PackageMeta:
    try:
        raw = json.loads(sidecar_of(package).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return PackageMeta()
    if not isinstance(raw, dict):
        return PackageMeta()
    return PackageMeta(
        include_packages=bool(raw.get("include_packages", True)),
        file_count=_as_int(raw.get("file_count")),
        exported_by=str(raw.get("exported_by") or ""),
    )


def _as_int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _backup_of(path: Path) -> LedgerBackup:
    stat = path.stat()
    return LedgerBackup(
        name=path.name,
        size=stat.st_size,
        created_at=datetime.fromtimestamp(stat.st_mtime, TZ),
        meta=read_meta(path),
    )


def list_backups(directory: Path) -> list[LedgerBackup]:
    """最新的在前；目录不存在时为空。"""
    backups = [_backup_of(path) for path in matching_files(directory, PACKAGE_NAME)]
    return sorted(backups, key=lambda item: (item.created_at, item.name), reverse=True)


def resolve_backup(directory: Path, name: str) -> Path:
    """校验文件名并返回路径；不合法、不存在或越出本账套备份目录一律 404。"""
    return resolve_in_dir(directory, name, PACKAGE_NAME, WHAT_PACKAGE)


def prune_backups(directory: Path, keep: int = KEEP_LEDGER_BACKUPS) -> None:
    """只保留最近 keep 份（连同侧车一起删）。"""
    prune_matching(directory, PACKAGE_NAME, keep, lambda path: (sidecar_of(path),))
