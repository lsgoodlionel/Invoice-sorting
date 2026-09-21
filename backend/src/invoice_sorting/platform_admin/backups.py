"""平台数据库（控制库 control.db）备份：仅 SaaS 部署，入口在平台后台。

控制库里是全部账套的账号、成员关系、会话、套餐与授权、平台邮件设置——
与任何单个账套的账本备份分开存放在平台根目录 `备份/平台/`，保留最近 KEEP_PLATFORM_BACKUPS 份。
用 SQLite 在线备份 API 复制，服务运行中也能得到一致的副本。
"""

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from invoice_sorting.common.backup_files import matching_files, prune_matching, resolve_in_dir
from invoice_sorting.common.errors import AppError
from invoice_sorting.config import Settings
from invoice_sorting.db.models import TZ, now

PLATFORM_BACKUPS_DIRNAME = "平台"
KEEP_PLATFORM_BACKUPS = 10
BACKUP_PREFIX = "control_"
BACKUP_NAME = re.compile(r"^control_\d{8}_\d{6}(?:_\d{1,3})?\.db$")
MAX_SAME_SECOND = 999
WHAT_BACKUP = "平台数据库备份"
MSG_BACKUP_FAILED = "平台数据库备份失败：{reason}"
MSG_TOO_MANY = "同一秒内的备份过多，请稍后再试"
NOTICE = (
    "平台数据库备份包含全部账号的密码哈希与加密后的邮件密码，请妥善保管。"
    "恢复时需同时具备原来的 secret.key（或环境变量 INVOICE_SORTING_SECRET_KEY），"
    "否则邮件发送密码无法解密，需要在平台后台重新填写。"
)


@dataclass(frozen=True)
class PlatformBackup:
    name: str
    size: int
    created_at: datetime

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "size": self.size, "created_at": self.created_at.isoformat()}


def platform_backups_dir(base: Settings) -> Path:
    """平台根目录下的平台备份区（base 为部署级配置，不是某个账套的）。"""
    return base.backup_dir / PLATFORM_BACKUPS_DIRNAME


def _target(directory: Path) -> Path:
    stamp = now().astimezone(TZ).strftime("%Y%m%d_%H%M%S")
    candidate = directory / f"{BACKUP_PREFIX}{stamp}.db"
    for index in range(2, MAX_SAME_SECOND + 1):
        if not candidate.exists():
            return candidate
        candidate = directory / f"{BACKUP_PREFIX}{stamp}_{index}.db"
    raise AppError(MSG_TOO_MANY, status_code=429)


def _copy(engine: Engine, target: Path) -> None:
    raw = engine.raw_connection()
    try:
        destination = sqlite3.connect(target)
        try:
            raw.driver_connection.backup(destination)
        finally:
            destination.close()
    except sqlite3.Error as error:
        target.unlink(missing_ok=True)
        raise AppError(MSG_BACKUP_FAILED.format(reason=error), status_code=500) from error
    finally:
        raw.close()


def _describe(path: Path) -> PlatformBackup:
    stat = path.stat()
    return PlatformBackup(
        name=path.name,
        size=stat.st_size,
        created_at=datetime.fromtimestamp(stat.st_mtime, TZ),
    )


def create_backup(base: Settings, engine: Engine) -> PlatformBackup:
    """在线备份控制库，然后只保留最近 KEEP_PLATFORM_BACKUPS 份。"""
    directory = platform_backups_dir(base)
    directory.mkdir(parents=True, exist_ok=True)
    target = _target(directory)
    _copy(engine, target)
    prune_matching(directory, BACKUP_NAME, KEEP_PLATFORM_BACKUPS)
    return _describe(target)


def list_backups(base: Settings) -> list[PlatformBackup]:
    """最新的在前。"""
    found = [_describe(path) for path in matching_files(platform_backups_dir(base), BACKUP_NAME)]
    return sorted(found, key=lambda item: (item.created_at, item.name), reverse=True)


def resolve_backup(base: Settings, name: str) -> Path:
    return resolve_in_dir(platform_backups_dir(base), name, BACKUP_NAME, WHAT_BACKUP)
