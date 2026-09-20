"""授权状态的持久化。

- **instance_id**：存放在 `data_dir/instance_id` 文本文件。选文件而不是数据库，是因为它是
  “这套安装”的身份：重建控制库、从备份恢复业务库都不应该换身份；运维也能直接打开查看，
  报给供应商做授权绑定。
- **令牌与校验结果**：存放在控制库 `license_token` 单行记录里，随控制库一起备份。
"""

import hashlib
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from invoice_sorting.config import Settings
from invoice_sorting.control.models import LicenseToken
from invoice_sorting.db.models import TZ, now
from invoice_sorting.licensing.state import LicenseSnapshot

logger = logging.getLogger(__name__)

INSTANCE_ID_FILENAME = "instance_id"
ROW_ID = 1
UUID_LENGTH = 36


def hash_license_key(license_key: str) -> str:
    """只保存密钥的摘要：配置换了密钥能发现，日志与数据库里都不出现明文。"""
    return hashlib.sha256((license_key or "").encode()).hexdigest()


def read_or_create_instance_id(settings: Settings) -> str:
    """读取实例标识；不存在或内容损坏时生成新的并落盘。"""
    path = settings.data_dir / INSTANCE_ID_FILENAME
    existing = _read_text(path)
    if _is_uuid(existing):
        return existing
    if existing:
        logger.warning("实例标识文件内容无法识别，已重新生成：%s", path)
    created = str(uuid.uuid4())
    _write_text(path, created)
    return created


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""
    except OSError:
        logger.exception("读取实例标识失败：%s", path)
        return ""


def _write_text(path: Path, value: str) -> None:
    """先写临时文件再替换，避免断电留下半截内容。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def _is_uuid(value: str) -> bool:
    if len(value) != UUID_LENGTH:
        return False
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def load_snapshot(db: Session, instance_id: str) -> LicenseSnapshot:
    """读取本地授权记录；首次启动时建立空记录（其 created_at 即宽限期起点）。"""
    row = db.get(LicenseToken, ROW_ID)
    if row is None:
        row = LicenseToken(id=ROW_ID, instance_id=instance_id, created_at=now())
        db.add(row)
        db.commit()
    return _to_snapshot(row)


def save_snapshot(db: Session, snapshot: LicenseSnapshot) -> None:
    """整体覆盖本地授权记录。"""
    row = db.get(LicenseToken, ROW_ID) or LicenseToken(id=ROW_ID)
    row.instance_id = snapshot.instance_id
    row.license_key_hash = snapshot.license_key_hash
    row.valid_until = snapshot.valid_until
    row.max_users = snapshot.max_users
    row.features = dict(snapshot.features)
    row.issued_at = snapshot.issued_at
    row.checked_at = snapshot.checked_at
    row.last_attempt_at = snapshot.last_attempt_at
    row.last_error = snapshot.last_error[:300]
    row.server_reachable = snapshot.server_reachable
    row.is_revoked = snapshot.is_revoked
    row.created_at = snapshot.created_at
    db.add(row)
    db.commit()


def _aware(value: datetime | None) -> datetime | None:
    """SQLite 读回的时间不带时区，统一补回 Asia/Shanghai。"""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=TZ)
    return value


def _to_snapshot(row: LicenseToken) -> LicenseSnapshot:
    return LicenseSnapshot(
        instance_id=row.instance_id,
        license_key_hash=row.license_key_hash,
        valid_until=_aware(row.valid_until),
        max_users=row.max_users,
        features=dict(row.features or {}),
        issued_at=_aware(row.issued_at),
        checked_at=_aware(row.checked_at),
        last_attempt_at=_aware(row.last_attempt_at),
        last_error=row.last_error,
        server_reachable=bool(row.server_reachable),
        is_revoked=bool(row.is_revoked),
        created_at=_aware(row.created_at) or now(),
    )
