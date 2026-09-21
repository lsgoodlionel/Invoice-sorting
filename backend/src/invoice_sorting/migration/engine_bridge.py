"""网页导入与导入引擎的接缝：预览（dry-run）与执行，统一成接口返回的报告形状。

合并导入引擎在 `migration.merge`（另行实现），约定签名：

    preview_import(runtime, control_factory, archive_path, slug, mode, include_settings=…)
    run_import(runtime, control_factory, archive_path, slug, mode, include_settings=…)

ImportReport 须能转成字典（`to_dict()`、dataclass 或 dict 均可）。

- 覆盖模式的**执行**始终走现有整套替换 `restore.import_tenant(overwrite=True)`：
  执行前自动把现有数据整包备份到 `备份/`，暂存解包全部校验通过后才替换正式目录；
- 引擎尚未随版本提供时，预览退回按清单统计的简要报告，合并模式的执行明确拒绝。
"""

import importlib
import logging
from dataclasses import asdict, is_dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session, sessionmaker

from invoice_sorting.common.errors import AppError
from invoice_sorting.config import LIBRARY_DIRNAME
from invoice_sorting.migration.manifest import SECTION_LIBRARY, Manifest
from invoice_sorting.migration.restore import import_tenant, read_manifest
from invoice_sorting.tenancy.runtime import TenantRuntime

logger = logging.getLogger(__name__)

ENGINE_MODULE = "invoice_sorting.migration.merge"
ENGINE_FUNCTIONS = ("preview_import", "run_import")
MODE_MERGE = "merge"
MODE_REPLACE = "replace"

MSG_MERGE_UNAVAILABLE = "当前版本尚未提供合并导入，请改用覆盖模式，或升级程序后再试"
MSG_REPORT_UNREADABLE = "导入报告格式无法识别，请查看服务端日志"
WARNING_ENGINE_MISSING = "当前版本尚未提供合并导入，以下仅为包内文件统计"
LABEL_FILES = "文件"


def load_engine() -> ModuleType | None:
    """取合并导入引擎；模块不存在或缺少约定函数时返回 None（模块内部导入出错照常抛出）。"""
    try:
        module = importlib.import_module(ENGINE_MODULE)
    except ModuleNotFoundError as error:
        if error.name != ENGINE_MODULE:
            raise
        return None
    if all(callable(getattr(module, name, None)) for name in ENGINE_FUNCTIONS):
        return module
    logger.warning("合并导入引擎缺少约定函数 %s，已按未提供处理", ENGINE_FUNCTIONS)
    return None


def is_mode_available(mode: str) -> bool:
    return mode == MODE_REPLACE or load_engine() is not None


def preview(
    runtime: TenantRuntime,
    control_factory: sessionmaker[Session],
    archive_path: Path,
    slug: str,
    mode: str,
    include_settings: bool = True,
) -> dict[str, Any]:
    """只读预览：将新增、跳过与冲突各多少。不写入任何数据。"""
    engine = load_engine()
    if engine is None:
        return _manifest_summary(read_manifest(archive_path), mode)
    report = engine.preview_import(
        runtime, control_factory, archive_path, slug, mode, include_settings=include_settings
    )
    return _normalized(report, mode, is_dry_run=True)


def execute(
    runtime: TenantRuntime,
    control_factory: sessionmaker[Session],
    archive_path: Path,
    slug: str,
    mode: str,
    include_settings: bool = True,
) -> dict[str, Any]:
    """真正导入。覆盖模式走整套替换（含覆盖前备份），合并模式交给引擎。"""
    if mode == MODE_REPLACE:
        return _replace(runtime, control_factory, archive_path, slug)
    engine = load_engine()
    if engine is None:
        raise AppError(MSG_MERGE_UNAVAILABLE)
    report = engine.run_import(
        runtime, control_factory, archive_path, slug, mode, include_settings=include_settings
    )
    return _normalized(report, mode, is_dry_run=False)


def _replace(
    runtime: TenantRuntime, control_factory: sessionmaker[Session], archive_path: Path, slug: str
) -> dict[str, Any]:
    result = import_tenant(runtime, control_factory, archive_path, slug, overwrite=True)
    summary = _manifest_summary(read_manifest(archive_path), MODE_REPLACE, is_dry_run=False)
    # 只给备份文件名，不暴露服务器上的绝对路径
    backup = result.backup_path.name if result.backup_path is not None else ""
    return {**summary, "warnings": [], "backup_file": backup}


def _normalized(report: Any, mode: str, is_dry_run: bool) -> dict[str, Any]:
    """引擎报告转成可 JSON 序列化的字典；引擎自己给出的字段优先。"""
    data = _as_dict(report)
    return jsonable_encoder({"mode": mode, "is_dry_run": is_dry_run, **data})


def _as_dict(report: Any) -> dict[str, Any]:
    if isinstance(report, dict):
        return report
    for name in ("to_dict", "to_payload"):
        method = getattr(report, name, None)
        if callable(method):
            value = method()
            if isinstance(value, dict):
                return value
    if is_dataclass(report) and not isinstance(report, type):
        return asdict(report)
    logger.error("无法识别的导入报告类型：%s", type(report).__name__)
    raise AppError(MSG_REPORT_UNREADABLE, status_code=500)


def _manifest_summary(manifest: Manifest, mode: str, is_dry_run: bool = True) -> dict[str, Any]:
    """引擎缺席或覆盖模式时的简要报告：按清单统计文件，形状与引擎报告一致。"""
    sections = manifest.sections()
    attachments = sections.get(SECTION_LIBRARY, {}).get("files", 0)
    items = [
        _section("attachments", LIBRARY_DIRNAME, attachments),
        _section("files", LABEL_FILES, len(manifest.files)),
    ]
    warnings = [WARNING_ENGINE_MISSING] if mode == MODE_MERGE else []
    return {
        "mode": mode,
        "is_dry_run": is_dry_run,
        "source": {
            "tenant": manifest.tenant_name,
            "exported_at": manifest.exported_at,
            "app_version": manifest.app_version,
        },
        "items": items,
        "warnings": warnings,
    }


def _section(key: str, label: str, added: int) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "added": added,
        "updated": 0,
        "skipped": 0,
        "conflicts": 0,
        "failed": 0,
        "details": [],
        "truncated": 0,
    }
