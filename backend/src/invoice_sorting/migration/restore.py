"""租户数据导入（设计 7）：校验搬迁包 → 落盘 → 补列迁移 → 登记到控制库。

落盘策略：先把包内文件解到租户目录下的临时暂存目录（同一磁盘，便于原子改名），
逐个核对大小与校验和；全部通过后才替换正式目录，因此校验失败不会破坏现有数据。
被替换的只有数据库、文件库，以及包内含资料包时的资料包目录；
`备份/` 与 `收件箱/` 始终保留。`--no-packages` 导出的包不会动目标已有的资料包。
"""

import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from invoice_sorting.common.errors import AppError, ConflictError
from invoice_sorting.config import (
    DB_FILENAME,
    LIBRARY_DIRNAME,
    PACKAGES_DIRNAME,
    Settings,
)
from invoice_sorting.control.migrate import MigrationReport, migrate_tenant_accounts
from invoice_sorting.control.repository import ensure_tenant, find_tenant, require_slug
from invoice_sorting.db.models import now
from invoice_sorting.migration.archive import (
    check_entries,
    extract_entry,
    open_archive,
    read_member,
)
from invoice_sorting.migration.export import export_tenant
from invoice_sorting.migration.manifest import (
    MANIFEST_NAME,
    MSG_NO_DATABASE,
    SECTION_PACKAGES,
    Manifest,
    check_schema_supported,
    parse_manifest,
)
from invoice_sorting.tenancy.runtime import TenantRuntime

logger = logging.getLogger(__name__)

STAGING_DIRNAME = ".导入暂存"
MANIFEST_MAX_BYTES = 64 * 1024 * 1024
SQLITE_SIDECARS = ("-wal", "-shm", "-journal")

MSG_ARCHIVE_MISSING = "搬迁包不存在：{path}"
MSG_TENANT_EXISTS = "账套 {slug} 已存在，如需覆盖请使用 --overwrite（会先备份现有数据）"


@dataclass(frozen=True)
class ImportResult:
    """导入结果：落盘统计、覆盖前备份位置与账号迁移情况。"""

    slug: str
    tenant_id: int
    file_count: int
    total_bytes: int
    backup_path: Path | None
    accounts: MigrationReport


def read_manifest(archive_path: Path) -> Manifest:
    """只读校验：解析清单、确认版本与文件清单可用（不落盘）。"""
    if not archive_path.is_file():
        raise AppError(MSG_ARCHIVE_MISSING.format(path=archive_path), status_code=404)
    with open_archive(archive_path) as archive:
        manifest = parse_manifest(read_member(archive, MANIFEST_NAME, MANIFEST_MAX_BYTES))
    check_schema_supported(manifest)
    check_entries(manifest)
    if not manifest.has_database:
        raise AppError(MSG_NO_DATABASE)
    return manifest


def import_tenant(
    runtime: TenantRuntime,
    control_factory: sessionmaker[Session],
    archive_path: Path,
    slug: str,
    overwrite: bool = False,
    moment: datetime | None = None,
) -> ImportResult:
    """把搬迁包导入为账套 slug；目标已存在时必须显式 overwrite。"""
    target_slug = require_slug(slug)
    manifest = read_manifest(archive_path)
    settings = runtime.base_settings.for_tenant(target_slug)
    is_existing = _is_existing(control_factory, settings, target_slug)
    if is_existing and not overwrite:
        raise ConflictError(MSG_TENANT_EXISTS.format(slug=target_slug))
    backup = _backup_existing(runtime, target_slug, moment) if is_existing else None
    runtime.evict(target_slug)  # 释放旧连接池，避免替换数据库文件时仍有句柄占用
    _unpack(archive_path, settings, manifest)
    tenant_id = _register(runtime, control_factory, target_slug, manifest)
    report = _sync_accounts(runtime, control_factory, target_slug, tenant_id)
    logger.info("账套 %s 已导入：%s 个文件", target_slug, len(manifest.files))
    return ImportResult(
        slug=target_slug,
        tenant_id=tenant_id,
        file_count=len(manifest.files),
        total_bytes=manifest.total_bytes,
        backup_path=backup,
        accounts=report,
    )


def _is_existing(factory: sessionmaker[Session], settings: Settings, slug: str) -> bool:
    if settings.db_path.exists():
        return True
    with factory() as control:
        return find_tenant(control, slug) is not None


def _backup_existing(runtime: TenantRuntime, slug: str, moment: datetime | None) -> Path | None:
    """覆盖前把现有数据整包备份到该账套的 `备份/` 目录。"""
    settings = runtime.base_settings.for_tenant(slug)
    if not settings.db_path.exists():
        return None
    stamp = moment or now()
    target = settings.backup_dir / f"覆盖前备份_{slug}_{stamp:%Y%m%d_%H%M%S}.zip"
    result = export_tenant(runtime.get(slug), target, tenant_name=slug, moment=stamp)
    return result.path


def _unpack(archive_path: Path, settings: Settings, manifest: Manifest) -> None:
    """解包到暂存目录并逐文件核对，全部通过后再替换正式目录。"""
    staging = settings.data_dir / STAGING_DIRNAME
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    try:
        with open_archive(archive_path) as archive:
            for entry in manifest.files:
                extract_entry(archive, entry, staging / entry.path)
        _swap_in(settings, staging, manifest)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _swap_in(settings: Settings, staging: Path, manifest: Manifest) -> None:
    _remove_database(settings)
    names = [LIBRARY_DIRNAME]
    if SECTION_PACKAGES in manifest.sections():
        names.append(PACKAGES_DIRNAME)
    for name in names:
        _replace_dir(settings.data_dir / name, staging / name)
    staged_db = staging / DB_FILENAME
    if staged_db.is_file():
        shutil.move(str(staged_db), str(settings.db_path))


def _remove_database(settings: Settings) -> None:
    """删除旧业务库及其 WAL 附属文件，避免新库继承旧的 -wal/-shm。"""
    settings.db_path.unlink(missing_ok=True)
    for suffix in SQLITE_SIDECARS:
        settings.db_path.with_name(settings.db_path.name + suffix).unlink(missing_ok=True)


def _replace_dir(current: Path, staged: Path) -> None:
    shutil.rmtree(current, ignore_errors=True)
    if staged.is_dir():
        shutil.move(str(staged), str(current))
    else:
        current.mkdir(parents=True, exist_ok=True)


def _register(
    runtime: TenantRuntime, factory: sessionmaker[Session], slug: str, manifest: Manifest
) -> int:
    """登记到控制库，并通过运行时完成建表补列与种子（设计 7）。"""
    with factory() as control:
        tenant = ensure_tenant(control, slug, manifest.tenant_name or slug)
        control.commit()
        tenant_id = tenant.id
    runtime.get(slug)
    return tenant_id


def _sync_accounts(
    runtime: TenantRuntime, factory: sessionmaker[Session], slug: str, tenant_id: int
) -> MigrationReport:
    """私有化包导入 SaaS：业务库里的账号与会话搬到控制库（幂等）。"""
    context = runtime.get(slug)
    with factory() as control:
        report = migrate_tenant_accounts(control, tenant_id, context.session_factory)
        control.commit()
    return report
