"""备份目录里文件的通用操作：按白名单列出、安全解析下载路径、只保留最近若干份。

账本备份包（migration.ledger_backups）与平台数据库备份（platform_admin.backups）共用。
文件名一律先过白名单正则，再确认解析后的路径就在该目录内，防止路径穿越与越权下载。
"""

import logging
import re
from collections.abc import Callable
from pathlib import Path

from invoice_sorting.common.errors import NotFoundError

logger = logging.getLogger(__name__)


def matching_files(directory: Path, pattern: re.Pattern[str]) -> list[Path]:
    """目录下文件名符合白名单的普通文件；目录不存在时为空。"""
    if not directory.is_dir():
        return []
    return [path for path in directory.iterdir() if path.is_file() and pattern.match(path.name)]


def resolve_in_dir(directory: Path, name: str, pattern: re.Pattern[str], what: str) -> Path:
    """校验文件名并返回路径；不合法、不存在或越出目录一律按“不存在”（404）处理。"""
    if not pattern.match(name or ""):
        raise NotFoundError(what)
    root = directory.resolve()
    path = (root / name).resolve()
    if path.parent != root or not path.is_file():
        raise NotFoundError(what)
    return path


def _age_key(path: Path) -> tuple[float, str]:
    return (path.stat().st_mtime, path.name)


def prune_matching(
    directory: Path,
    pattern: re.Pattern[str],
    keep: int,
    companions: Callable[[Path], tuple[Path, ...]] = lambda _path: (),
) -> None:
    """只保留最近 keep 份（按修改时间，同时间按文件名）；companions 给出需一并删除的附属文件。"""
    ordered = sorted(matching_files(directory, pattern), key=_age_key)
    stale = ordered[:-keep] if keep > 0 else ordered
    for old in stale:
        try:
            old.unlink()
            for extra in companions(old):
                extra.unlink(missing_ok=True)
        except OSError:
            logger.warning("清理旧备份失败：%s", old)
        else:
            logger.info("已清理旧备份 %s", old.name)
