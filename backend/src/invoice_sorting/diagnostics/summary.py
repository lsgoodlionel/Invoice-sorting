"""summary.json：环境与规模摘要（设计《日志与故障上报》3）。

只写**量级**不写数据：账套数、记录数的数量级区间，足以判断“是不是数据量引起的”，
但拿不到任何一条具体记录。
"""

import platform
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from invoice_sorting.config import DB_FILENAME, TENANTS_DIRNAME, Settings
from invoice_sorting.diagnostics import system
from invoice_sorting.diagnostics.fingerprint import Fault
from invoice_sorting.licensing.constants import app_version

SERVICE_START_COMMAND = ("systemctl", "show", "-p", "ActiveEnterTimestamp", "--value")
COUNTED_TABLES = ("expense", "attachment")
MAGNITUDE_EDGES = (0, 10, 100, 1000, 10000, 100000)
MAGNITUDE_OVERFLOW = "100000+"
MAGNITUDE_UNKNOWN = "未知"
# 代码目录固定，避免 git 命令受调用者当前目录影响
REPO_ROOT = Path(__file__).resolve().parents[3]
GIT_COMMAND = ("git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD")


def build_summary(settings: Settings, reason: str, fault: Fault | None) -> dict[str, Any]:
    """汇总应用版本、部署形态、系统与磁盘信息，以及账套与记录的数量级。"""
    return {
        "reason": reason,
        "fingerprint": fault.fingerprint if fault is not None else "",
        "exception": fault.exc_type if fault is not None else "",
        "location": fault.location if fault is not None else "",
        "app_version": app_version(),
        "git_commit": system.run_command(GIT_COMMAND),
        "deployment_mode": settings.deployment_mode,
        "auth_enabled": settings.auth_enabled,
        "license_configured": settings.is_license_configured,
        "upload_configured": settings.is_log_upload_configured,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "service_started_at": system.run_command(
            (*SERVICE_START_COMMAND, "invoice-sorting.service")
        ),
        "disk": _disk_usage(settings.data_dir),
        "memory": _memory_info(),
        "scale": _scale(settings),
    }


def _disk_usage(path: Path) -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(path if path.exists() else path.anchor or "/")
    except OSError:
        return {"error": "无法读取磁盘信息"}
    return {"total_mb": usage.total // 1024**2, "free_mb": usage.free // 1024**2}


def _memory_info() -> dict[str, Any]:
    """Linux 下从 /proc/meminfo 取总量与可用量；其他系统直接说明不可用。"""
    try:
        raw = Path("/proc/meminfo").read_text(encoding="utf-8")
    except OSError:
        return {"error": "本系统不提供 /proc/meminfo"}
    fields = dict(_meminfo_rows(raw))
    return {
        "total_mb": fields.get("MemTotal", 0) // 1024,
        "available_mb": fields.get("MemAvailable", 0) // 1024,
    }


def _meminfo_rows(raw: str):
    for line in raw.splitlines():
        name, _, rest = line.partition(":")
        number = rest.strip().split(" ")[0]
        if number.isdigit():
            yield name, int(number)


def _scale(settings: Settings) -> dict[str, Any]:
    """账套数与各表记录的数量级；读不到库时写“未知”，不影响其余内容。"""
    databases = _tenant_databases(settings)
    return {
        "tenants": len(databases),
        "records": {table: _magnitude(_count_rows(databases, table)) for table in COUNTED_TABLES},
    }


def _tenant_databases(settings: Settings) -> tuple[Path, ...]:
    root = settings.data_dir / DB_FILENAME
    found = [root] if root.exists() else []
    tenants_dir = settings.data_dir / TENANTS_DIRNAME
    if tenants_dir.is_dir():
        found.extend(sorted(tenants_dir.glob(f"*/{DB_FILENAME}")))
    return tuple(found)


def _count_rows(databases: tuple[Path, ...], table: str) -> int | None:
    total = 0
    counted = False
    for path in databases:
        rows = _count_one(path, table)
        if rows is not None:
            total += rows
            counted = True
    return total if counted else None


def _count_one(path: Path, table: str) -> int | None:
    """只读打开业务库数一行数；库被锁、表不存在等都返回 None。"""
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1)
    except (sqlite3.Error, OSError):
        return None
    with closing(connection):
        try:
            statement = f"SELECT COUNT(*) FROM {table}"  # noqa: S608 - 表名取自代码内常量
            return int(connection.execute(statement).fetchone()[0])
        except (sqlite3.Error, TypeError, ValueError):
            return None


def _magnitude(count: int | None) -> str:
    """把精确条数折算成区间，避免通过数量反推业务规模细节。"""
    if count is None:
        return MAGNITUDE_UNKNOWN
    for low, high in zip(MAGNITUDE_EDGES, MAGNITUDE_EDGES[1:], strict=False):
        if count <= high:
            return f"{low}-{high}"
    return MAGNITUDE_OVERFLOW
