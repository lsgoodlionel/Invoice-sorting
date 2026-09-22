"""租户数据导入（设计 7）：校验搬迁包 → 落盘 → 补列迁移 → 登记到控制库。

落盘策略：先把包内文件解到租户目录下的临时暂存目录（同一磁盘，便于原子改名），
逐个核对大小与校验和；全部通过后才替换正式目录，因此校验失败不会破坏现有数据。
被替换的只有数据库、文件库，以及包内含资料包时的资料包目录；
`备份/` 与 `收件箱/` 始终保留。`--no-packages` 导出的包不会动目标已有的资料包。

登录账号（账本搬迁设计 3.1）：只有**单账套部署**且包内带 accounts.json 时才恢复账号，
解包前先做只读检查（恢复后没有可用管理员就中止，不写任何数据）；解包后在一个控制库事务里写回，
万一失败则回滚控制库，并用覆盖前的整包备份把账套数据还原回去。SaaS 部署一律不动账号。
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
from invoice_sorting.control.members import list_members
from invoice_sorting.control.migrate import MigrationReport, migrate_tenant_accounts
from invoice_sorting.control.repository import ensure_tenant, find_tenant, require_slug
from invoice_sorting.db.models import now
from invoice_sorting.migration.accounts_export import collect_accounts
from invoice_sorting.migration.accounts_file import AccountsFile, read_accounts
from invoice_sorting.migration.accounts_restore import (
    AccountsRestoreResult,
    business_usernames,
    invalidate_sessions,
    preflight,
    restore_accounts,
)
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
    SECTION_ACCOUNTS,
    SECTION_PACKAGES,
    Manifest,
    check_schema_supported,
    parse_manifest,
)
from invoice_sorting.tenancy.runtime import TenantContext, TenantRuntime
from invoice_sorting.users.deletion import MIRROR_USERNAME_MAX, mark_mirror_deleted
from invoice_sorting.users.mirror import sync_members_mirror
from invoice_sorting.users.repository import find_user

logger = logging.getLogger(__name__)

STAGING_DIRNAME = ".导入暂存"
# 解包区放在暂存目录的子目录里：整个 `.导入暂存` 还存着网页分片上传的会话，不能整体清空
UNPACK_DIRNAME = ".解包"
MANIFEST_MAX_BYTES = 64 * 1024 * 1024
SQLITE_SIDECARS = ("-wal", "-shm", "-journal")

MSG_ARCHIVE_MISSING = "搬迁包不存在：{path}"
MSG_TENANT_EXISTS = "账套 {slug} 已存在，如需覆盖请使用 --overwrite（会先备份现有数据）"
MSG_ACCOUNTS_FAILED = "恢复登录账号失败，账套数据已回滚到覆盖前的状态，登录账号未改动"
MSG_ROLLBACK_FAILED = "恢复登录账号失败，且自动回滚账套数据也失败：请用备份 {backup} 手动恢复"


@dataclass(frozen=True)
class ImportResult:
    """导入结果：落盘统计、覆盖前备份位置与账号迁移情况。"""

    slug: str
    tenant_id: int
    file_count: int
    total_bytes: int
    backup_path: Path | None
    accounts: MigrationReport
    # 包内带的登录账号个数，以及单账套覆盖时实际恢复的结果（SaaS 或旧包为 None）
    package_accounts: int = 0
    restored_accounts: AccountsRestoreResult | None = None


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


def import_tenant(  # noqa: PLR0913 - 与命令行参数一一对应
    runtime: TenantRuntime,
    control_factory: sessionmaker[Session],
    archive_path: Path,
    slug: str,
    overwrite: bool = False,
    moment: datetime | None = None,
    actor_id: int | None = None,
) -> ImportResult:
    """把搬迁包导入为账套 slug；目标已存在时必须显式 overwrite。

    actor_id 为执行导入的账号（网页导入的当前管理员；命令行为 None）：恢复账号时不删除他本人。
    """
    target_slug = require_slug(slug)
    manifest = read_manifest(archive_path)
    settings = runtime.base_settings.for_tenant(target_slug)
    is_existing = _is_existing(control_factory, settings, target_slug)
    if is_existing and not overwrite:
        raise ConflictError(MSG_TENANT_EXISTS.format(slug=target_slug))
    package_accounts = read_accounts(archive_path, manifest)
    to_restore = _accounts_to_restore(
        runtime, control_factory, target_slug, package_accounts, actor_id
    )
    backup = (
        _backup_existing(runtime, control_factory, target_slug, moment) if is_existing else None
    )
    runtime.evict(target_slug)  # 释放旧连接池，避免替换数据库文件时仍有句柄占用
    _unpack(archive_path, settings, manifest)
    tenant_id = _register(control_factory, target_slug, manifest)
    restored = _restore_or_roll_back(
        runtime, control_factory, target_slug, tenant_id, to_restore, backup
    )
    report = _sync_accounts(runtime, control_factory, target_slug, tenant_id, restored)
    logger.info("账套 %s 已导入：%s 个文件", target_slug, len(manifest.files))
    return ImportResult(
        slug=target_slug,
        tenant_id=tenant_id,
        file_count=len(manifest.files),
        total_bytes=manifest.total_bytes,
        backup_path=backup,
        accounts=report,
        package_accounts=package_accounts.count if package_accounts is not None else 0,
        restored_accounts=restored,
    )


@dataclass(frozen=True)
class _AccountsJob:
    """本次要恢复的账号与执行者（执行者本人不会因备份里没有而被删除）。"""

    accounts: AccountsFile
    actor_id: int | None


def _accounts_to_restore(
    runtime: TenantRuntime,
    factory: sessionmaker[Session],
    slug: str,
    accounts: AccountsFile | None,
    actor_id: int | None,
) -> _AccountsJob | None:
    """只有单账套部署才恢复账号；先只读检查，恢复后没有可用管理员就在写入任何数据前中止。"""
    if accounts is None or runtime.base_settings.is_saas:
        return None
    with factory() as control:
        tenant = find_tenant(control, slug)
        tenant_id = tenant.id if tenant is not None else None
    preflight(factory, tenant_id, accounts, actor_id)
    return _AccountsJob(accounts=accounts, actor_id=actor_id)


def _restore_or_roll_back(  # noqa: PLR0913 - 恢复与回滚需要的全部句柄
    runtime: TenantRuntime,
    factory: sessionmaker[Session],
    slug: str,
    tenant_id: int,
    job: _AccountsJob | None,
    backup: Path | None,
) -> AccountsRestoreResult | None:
    """写回账号；失败时控制库已回滚，再用覆盖前备份还原账套数据。异常细节不外露（可能含哈希）。"""
    if job is None:
        return None
    db_path = runtime.base_settings.for_tenant(slug).db_path
    try:
        users = business_usernames(db_path)
        return restore_accounts(factory, tenant_id, job.accounts, users, job.actor_id)
    except Exception as error:
        logger.error("账套 %s 恢复登录账号失败（%s），回滚账套数据", slug, _kind(error))
        _roll_back_data(runtime, slug, backup)
        if isinstance(error, AppError):
            raise
        raise AppError(MSG_ACCOUNTS_FAILED, status_code=500) from None


def _kind(error: Exception) -> str:
    return error.message if isinstance(error, AppError) else type(error).__name__


def _roll_back_data(runtime: TenantRuntime, slug: str, backup: Path | None) -> None:
    """用覆盖前的整包备份还原数据库与文件库；导入前还没有数据库（没有备份）时撤掉刚解出的内容。"""
    runtime.evict(slug)
    settings = runtime.base_settings.for_tenant(slug)
    if backup is None:
        _discard_unpacked(settings)
        return
    try:
        _unpack(backup, settings, read_manifest(backup))
    except Exception as error:
        logger.error("自动回滚账套数据失败（%s），备份：%s", type(error).__name__, backup)
        raise AppError(MSG_ROLLBACK_FAILED.format(backup=backup.name), status_code=500) from None


def _discard_unpacked(settings: Settings) -> None:
    """回到“什么都没导入”：撤掉刚换进来的数据库、文件库与资料包（备份与收件箱不动）。"""
    _remove_database(settings)
    for name in (LIBRARY_DIRNAME, PACKAGES_DIRNAME):
        shutil.rmtree(settings.data_dir / name, ignore_errors=True)
    logger.warning("账套数据目录 %s 导入前没有数据库，已撤掉本次解出的内容", settings.data_dir.name)


def _is_existing(factory: sessionmaker[Session], settings: Settings, slug: str) -> bool:
    if settings.db_path.exists():
        return True
    with factory() as control:
        return find_tenant(control, slug) is not None


def _backup_existing(
    runtime: TenantRuntime, factory: sessionmaker[Session], slug: str, moment: datetime | None
) -> Path | None:
    """覆盖前把现有数据整包备份到该账套的 `备份/` 目录（单账套连同当前登录账号）。"""
    settings = runtime.base_settings.for_tenant(slug)
    if not settings.db_path.exists():
        return None
    stamp = moment or now()
    target = settings.backup_dir / f"覆盖前备份_{slug}_{stamp:%Y%m%d_%H%M%S}.zip"
    accounts = collect_accounts(factory, runtime.base_settings, slug)
    result = export_tenant(
        runtime.get(slug), target, tenant_name=slug, moment=stamp, accounts=accounts
    )
    return result.path


def _unpack(archive_path: Path, settings: Settings, manifest: Manifest) -> None:
    """解包到暂存目录并逐文件核对，全部通过后再替换正式目录。"""
    staging = settings.data_dir / STAGING_DIRNAME / UNPACK_DIRNAME
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    try:
        with open_archive(archive_path) as archive:
            for entry in manifest.files:
                if entry.section == SECTION_ACCOUNTS:
                    continue  # 账号清单只在内存里读取，不落盘
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


def _register(factory: sessionmaker[Session], slug: str, manifest: Manifest) -> int:
    """登记到控制库（设计 7）；业务库的建表补列与种子在随后打开运行时时完成。"""
    with factory() as control:
        tenant = ensure_tenant(control, slug, manifest.tenant_name or slug)
        control.commit()
        return tenant.id


def _sync_accounts(
    runtime: TenantRuntime,
    factory: sessionmaker[Session],
    slug: str,
    tenant_id: int,
    restored: AccountsRestoreResult | None,
) -> MigrationReport:
    """打开业务库；私有化包导入 SaaS 时把业务库里的账号与会话搬到控制库（幂等）。

    恢复过账号时：先把被删除账号的镜像行标记为已删除（否则迁移会按镜像行把账号“复活”）；
    旧版业务库里残留的会话可能被搬进来，因此对受影响账号再做一次会话失效，
    并按控制库成员补齐业务库镜像（命令行没有首次加载回调，这里显式同步）。
    """
    context = runtime.get(slug)
    invalidated = restored.invalidated_ids if restored is not None else ()
    if restored is not None:
        _mark_deleted(context, restored.deleted)
    with factory() as control:
        report = migrate_tenant_accounts(control, tenant_id, context.session_factory)
        invalidate_sessions(control, invalidated)
        control.commit()
    if restored is not None:
        _sync_mirror(factory, context, tenant_id)
    return report


def _mark_deleted(context: TenantContext, deleted: tuple[tuple[int, str], ...]) -> None:
    """新业务库来自备份，id 不一定对得上被删的本地账号：按用户名找镜像行标记已删除。"""
    if not deleted:
        return
    with context.session_factory() as business:
        for _, username in deleted:
            user = find_user(business, username[:MIRROR_USERNAME_MAX])
            if user is not None:
                mark_mirror_deleted(business, user.id, user.username)
        business.commit()


def _sync_mirror(factory: sessionmaker[Session], context: TenantContext, tenant_id: int) -> None:
    with factory() as control:
        members = list_members(control, tenant_id)
    with context.session_factory() as business:
        sync_members_mirror(business, members)
        business.commit()
