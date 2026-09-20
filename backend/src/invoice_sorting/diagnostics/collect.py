"""收集并打包诊断包（设计《日志与故障上报》3 诊断包）。

流程固定：**收集 → 脱敏 → 截断 → 打包 → 残留自检**。
脱敏在写盘之前完成，本机留存的包与上传的包内容一致，不存在“本地没脱敏被误发”的路径。
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from invoice_sorting.config import Settings
from invoice_sorting.diagnostics import system
from invoice_sorting.diagnostics.constants import (
    ENV_SET,
    ENV_UNSET,
    JOURNAL_TAIL_LINES,
    KEEP_PACKAGES,
    LOG_TAIL_LINES,
    MAX_PACKAGE_BYTES,
    MEMBER_APP_LOG,
    MEMBER_ENV,
    MEMBER_HEALTH,
    MEMBER_JOURNAL,
    MEMBER_NGINX,
    MEMBER_SERVICE,
    MEMBER_SUMMARY,
    NGINX_ERROR_LOG,
    NGINX_TAIL_LINES,
    PACKAGE_PREFIX,
    PACKAGE_SUFFIX,
    SERVICE_UNIT,
    TRACKED_ENV_NAMES,
    TRUNCATION_NOTE,
    TRUNCATION_ORDER,
)
from invoice_sorting.diagnostics.fingerprint import Fault
from invoice_sorting.diagnostics.redaction import redact_mapping, residue_in_mapping
from invoice_sorting.diagnostics.summary import build_summary

logger = logging.getLogger(__name__)

TIME_FORMAT = "%Y%m%d-%H%M%S"
NO_FINGERPRINT = "nofp"


@dataclass(frozen=True)
class DiagnosticPackage:
    """一次打包的结果；整体替换，不就地修改。"""

    path: Path
    size: int
    reason: str
    fingerprint: str
    created_at: datetime
    residue: tuple[str, ...] = ()
    is_truncated: bool = False

    @property
    def is_safe_to_upload(self) -> bool:
        """残留自检通过才允许上传。"""
        return not self.residue


def collect_package(
    settings: Settings,
    reason: str,
    created_at: datetime,
    fault: Fault | None = None,
    health: dict[str, Any] | None = None,
) -> DiagnosticPackage:
    """生成诊断包并返回其路径与自检结果。"""
    parts = redact_mapping(_gather(settings, reason, fault, health))
    trimmed, is_truncated = _truncate(parts)
    path = _package_path(settings, created_at, fault)
    _write_zip(path, trimmed)
    prune_packages(settings.diagnostics_dir)
    return DiagnosticPackage(
        path=path,
        size=path.stat().st_size,
        reason=reason,
        fingerprint=fault.fingerprint if fault is not None else "",
        created_at=created_at,
        residue=residue_in_mapping(trimmed),
        is_truncated=is_truncated,
    )


def _gather(
    settings: Settings, reason: str, fault: Fault | None, health: dict[str, Any] | None
) -> dict[str, str]:
    """按设计第 3 节的表格逐项收集；取不到的项写明原因而不是消失。"""
    return {
        MEMBER_SUMMARY: _as_json(build_summary(settings, reason, fault)),
        MEMBER_APP_LOG: system.read_tail(settings.log_file, LOG_TAIL_LINES),
        MEMBER_JOURNAL: system.run_command(
            ("journalctl", "-u", SERVICE_UNIT, "-n", str(JOURNAL_TAIL_LINES), "--no-pager")
        ),
        MEMBER_SERVICE: system.run_command(("systemctl", "status", SERVICE_UNIT, "--no-pager")),
        MEMBER_NGINX: system.read_tail(Path(NGINX_ERROR_LOG), NGINX_TAIL_LINES),
        MEMBER_ENV: system.env_presence(TRACKED_ENV_NAMES, ENV_SET, ENV_UNSET),
        MEMBER_HEALTH: _as_json(health if health is not None else {}),
    }


def _as_json(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):  # pragma: no cover - default=str 已兜住绝大多数情况
        return "{}"


def _truncate(parts: dict[str, str]) -> tuple[dict[str, str], bool]:
    """超出体积上限时按 TRUNCATION_ORDER 依次截断日志，返回新字典。"""
    trimmed = dict(parts)
    is_truncated = False
    for name in TRUNCATION_ORDER:
        if _total_bytes(trimmed) <= MAX_PACKAGE_BYTES:
            break
        budget = MAX_PACKAGE_BYTES - _total_bytes({k: v for k, v in trimmed.items() if k != name})
        trimmed[name] = _cut(trimmed.get(name, ""), max(budget, 0))
        is_truncated = True
    return trimmed, is_truncated


def _total_bytes(parts: dict[str, str]) -> int:
    return sum(len(content.encode("utf-8")) for content in parts.values())


def _cut(content: str, budget: int) -> str:
    """保留尾部（最近的日志最有用），并写明已截断。"""
    keep = max(budget - len(TRUNCATION_NOTE.encode("utf-8")), 0)
    raw = content.encode("utf-8")[-keep:] if keep else b""
    return TRUNCATION_NOTE + raw.decode("utf-8", errors="ignore")


def _package_path(settings: Settings, created_at: datetime, fault: Fault | None) -> Path:
    short = fault.short if fault is not None else NO_FINGERPRINT
    name = (
        f"{PACKAGE_PREFIX}_{system.host_short_name()}_"
        f"{created_at.strftime(TIME_FORMAT)}_{short}{PACKAGE_SUFFIX}"
    )
    settings.diagnostics_dir.mkdir(parents=True, exist_ok=True)
    return settings.diagnostics_dir / name


def _write_zip(path: Path, parts: dict[str, str]) -> None:
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)


def prune_packages(directory: Path, keep: int = KEEP_PACKAGES) -> None:
    """只保留最近 keep 个诊断包；删除失败只记日志，不影响本次生成。"""
    try:
        found = list(directory.glob(f"{PACKAGE_PREFIX}_*{PACKAGE_SUFFIX}"))
        packages = sorted(found, key=lambda item: (item.stat().st_mtime_ns, item.name))
    except OSError:
        return
    for stale in packages[:-keep] if keep > 0 else packages:
        try:
            stale.unlink()
        except OSError:
            logger.info("清理旧诊断包失败：%s", stale.name)
