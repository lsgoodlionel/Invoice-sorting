"""覆盖模式的预览与执行报告（账本搬迁设计 3）：整体替换不需要逐条判重，只说明范围与后果。"""

from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from invoice_sorting.common.errors import AppError
from invoice_sorting.control.repository import find_tenant, require_slug
from invoice_sorting.migration.manifest import SECTION_LIBRARY, SECTION_PACKAGES
from invoice_sorting.migration.package import ImportRejectedError, PackageInfo, inspect_package
from invoice_sorting.migration.report import (
    SECTION_ATTACHMENTS,
    SECTION_BATCHES,
    SECTION_EXPORTS,
    SECTION_RECORDS,
    SectionReport,
)
from invoice_sorting.migration.restore import ImportResult, import_tenant
from invoice_sorting.tenancy.runtime import TenantRuntime

MODE_REPLACE = "replace"
WARN_REPLACE = "覆盖模式会用包内数据整体替换账套 {slug} 的现有数据，执行前自动整包备份到“备份/”"
WARN_NEW_TENANT = "账套 {slug} 尚不存在，将按包内数据新建"


def _sections(info: PackageInfo) -> dict[str, dict[str, object]]:
    """包内范围：新包取 ledger.json 的统计，旧包只能按清单数附件文件。"""
    manifest_sections = info.manifest.sections()
    files = manifest_sections.get(SECTION_LIBRARY, {}).get("files", 0)
    packages = manifest_sections.get(SECTION_PACKAGES, {}).get("files", 0)
    scope = info.ledger.scope if info.ledger is not None else None
    counts = {
        SECTION_RECORDS: scope.records if scope else 0,
        SECTION_ATTACHMENTS: scope.attachments if scope else files,
        SECTION_BATCHES: scope.batches if scope else 0,
        SECTION_EXPORTS: packages,
    }
    return {key: SectionReport(added=value).to_dict(key) for key, value in counts.items()}


def _target_exists(
    runtime: TenantRuntime, control_factory: sessionmaker[Session], slug: str
) -> bool:
    if runtime.base_settings.for_tenant(slug).db_path.exists():
        return True
    with control_factory() as control:
        return find_tenant(control, slug) is not None


def _normalized_slug(slug: str) -> str:
    try:
        return require_slug(slug)
    except AppError as error:
        raise ImportRejectedError(error.message) from error


def preview_replace(
    runtime: TenantRuntime, control_factory: sessionmaker[Session], archive_path: Path, slug: str
) -> dict[str, object]:
    """只读：包内范围与目标账套是否存在；不写入任何数据。"""
    info = inspect_package(archive_path)
    normalized = _normalized_slug(slug)
    exists = _target_exists(runtime, control_factory, normalized)
    warning = WARN_REPLACE if exists else WARN_NEW_TENANT
    return {
        "mode": MODE_REPLACE,
        "slug": normalized,
        "is_dry_run": True,
        "source": info.summary(),
        "target_exists": exists,
        "items": list(_sections(info).values()),
        "warnings": [warning.format(slug=normalized)],
    }


def replace_report(archive_path: Path, slug: str, result: ImportResult) -> dict[str, object]:
    """整套替换完成后的报告；备份只给文件名，不暴露服务器上的绝对路径。"""
    info = inspect_package(archive_path)
    backup = result.backup_path.name if result.backup_path is not None else ""
    return {
        "mode": MODE_REPLACE,
        "slug": result.slug or slug,
        "is_dry_run": False,
        "source": info.summary(),
        "target_exists": backup != "",
        "backup_file": backup,
        "items": list(_sections(info).values()),
        "warnings": [],
    }


def run_replace(
    runtime: TenantRuntime, control_factory: sessionmaker[Session], archive_path: Path, slug: str
) -> dict[str, object]:
    """整套替换（调用方已完成二次确认）：沿用 restore 的备份与暂存切换逻辑。"""
    inspect_package(archive_path)
    result = import_tenant(runtime, control_factory, archive_path, slug, overwrite=True)
    return replace_report(archive_path, slug, result)
