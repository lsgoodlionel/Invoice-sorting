"""应用设置（键值表）与数据库在线备份。"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from invoice_sorting.common.errors import AppError
from invoice_sorting.config import Settings
from invoice_sorting.db.models import TZ, AppSetting

logger = logging.getLogger(__name__)

DEFAULT_OVERDUE_DAYS = 30
MAX_OVERDUE_DAYS = 3650
BACKUP_KEEP = 10
BACKUP_PREFIX = "invoice_"
TEXT_KEYS = ("buyer_name", "buyer_tax_id")
INT_KEYS = ("overdue_days",)


def get_app_settings(session: Session) -> dict[str, Any]:
    stored = {row.key: row.value for row in session.scalars(select(AppSetting))}
    overdue = stored.get("overdue_days", "")
    return {
        "buyer_name": stored.get("buyer_name", ""),
        "buyer_tax_id": stored.get("buyer_tax_id", ""),
        "overdue_days": int(overdue) if overdue.isdigit() else DEFAULT_OVERDUE_DAYS,
    }


def _normalize(key: str, value: Any) -> str:
    if key in TEXT_KEYS:
        return str(value or "").strip()
    if key in INT_KEYS:
        if isinstance(value, bool) or not isinstance(value, int):
            raise AppError("超期提醒天数必须是整数")
        if not 1 <= value <= MAX_OVERDUE_DAYS:
            raise AppError(f"超期提醒天数需在 1–{MAX_OVERDUE_DAYS} 之间")
        return str(value)
    raise AppError(f"未知设置项：{key}")


def update_app_settings(session: Session, **values: Any) -> dict[str, Any]:
    normalized = {key: _normalize(key, value) for key, value in values.items()}
    for key, value in normalized.items():
        row = session.get(AppSetting, key)
        if row is None:
            session.add(AppSetting(key=key, value=value))
        else:
            row.value = value
    session.flush()
    return get_app_settings(session)


def buyer_identity(session: Session) -> tuple[str, str]:
    values = get_app_settings(session)
    return values["buyer_name"], values["buyer_tax_id"]


def _timestamp() -> str:
    return datetime.now(TZ).strftime("%Y%m%d_%H%M%S")


def _prune_backups(backup_dir: Path) -> None:
    backups = sorted(backup_dir.glob(f"{BACKUP_PREFIX}*.db"), key=lambda path: path.name)
    for old in backups[:-BACKUP_KEEP]:
        old.unlink()
        logger.info("已清理旧备份 %s", old.name)


def backup_database(settings: Settings, engine: Engine) -> Path:
    """用 SQLite 在线备份 API 复制数据库到备份目录，保留最近 10 份。"""
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = _timestamp()
    target = settings.backup_dir / f"{BACKUP_PREFIX}{stamp}.db"
    index = 2
    while target.exists():
        target = settings.backup_dir / f"{BACKUP_PREFIX}{stamp}_{index}.db"
        index += 1
    raw = engine.raw_connection()
    try:
        destination = sqlite3.connect(target)
        try:
            raw.driver_connection.backup(destination)
        finally:
            destination.close()
    finally:
        raw.close()
    _prune_backups(settings.backup_dir)
    return target
