"""覆盖模式的预览与执行报告（账本搬迁设计 3）：整体替换不需要逐条判重，只说明范围与后果。

单账套部署且包内带账号时多一个 `accounts` 分区（每个账号是新建、更新密码还是不变）
与顶层 `accounts` 说明；SaaS 目标只说明“不导入账号”。
"""

from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from invoice_sorting.common.errors import AppError
from invoice_sorting.control.repository import find_tenant, require_slug
from invoice_sorting.migration.accounts_plan import build_plan, load_local_accounts, plan_section
from invoice_sorting.migration.accounts_report import (
    NOTE_RESTORE,
    NOTE_RESTORED,
    WARN_NO_ADMIN,
    accounts_info,
    accounts_item,
    saas_accounts_info,
)
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
NOTE_SETTINGS = "覆盖模式整体替换数据库：系统设置、分类、凭证规则与分类记忆一并以导入包为准"


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


def _accounts_preview(
    runtime: TenantRuntime,
    control_factory: sessionmaker[Session],
    info: PackageInfo,
    slug: str,
    actor_id: int | None,
) -> dict[str, object]:
    """账号部分的预览：items 追加的分区、警告与顶层说明（没有账号时全为空）。"""
    if info.accounts is None:
        return {"items": [], "warnings": [], "accounts": None}
    if runtime.base_settings.is_saas:
        return {"items": [], "warnings": [], "accounts": saas_accounts_info(info.account_count)}
    with control_factory() as control:
        tenant = find_tenant(control, slug)
        local = load_local_accounts(control, tenant.id if tenant is not None else None)
    plan = build_plan(info.accounts.accounts, local, actor_id=actor_id)
    return {
        "items": [accounts_item(plan_section(plan))],
        "warnings": [] if plan.has_usable_admin else [WARN_NO_ADMIN],
        "accounts": accounts_info(info.account_count, will_restore=True, note=NOTE_RESTORE),
    }


def _with_accounts(report: dict[str, object], accounts: dict[str, object]) -> dict[str, object]:
    """把账号部分并入报告（不可变：返回新字典）。"""
    merged = {
        **report,
        "items": [*report["items"], *accounts["items"]],
        "warnings": [*accounts["warnings"], *report["warnings"]],
    }
    return {**merged, "accounts": accounts["accounts"]} if accounts["accounts"] else merged


def preview_replace(
    runtime: TenantRuntime,
    control_factory: sessionmaker[Session],
    archive_path: Path,
    slug: str,
    actor_id: int | None = None,
) -> dict[str, object]:
    """只读：包内范围、目标账套是否存在与（单账套）账号去向；不写入任何数据。

    actor_id 为将要执行导入的账号：备份里没有他时预览里标为保留而不是删除。
    """
    info = inspect_package(archive_path)
    normalized = _normalized_slug(slug)
    exists = _target_exists(runtime, control_factory, normalized)
    warning = WARN_REPLACE if exists else WARN_NEW_TENANT
    report = {
        "mode": MODE_REPLACE,
        "slug": normalized,
        "is_dry_run": True,
        "source": info.summary(),
        "target_exists": exists,
        "include_settings": True,
        "items": list(_sections(info).values()),
        "warnings": [warning.format(slug=normalized), NOTE_SETTINGS],
    }
    accounts = _accounts_preview(runtime, control_factory, info, normalized, actor_id)
    return _with_accounts(report, accounts)


def _accounts_result(info: PackageInfo, result: ImportResult) -> dict[str, object]:
    restored = result.restored_accounts
    if restored is not None:
        note = accounts_info(restored.count, will_restore=True, note=NOTE_RESTORED)
        return {"items": [accounts_item(restored.section)], "warnings": [], "accounts": note}
    note = saas_accounts_info(info.account_count)
    return {"items": [], "warnings": [], "accounts": note}


def replace_report(archive_path: Path, slug: str, result: ImportResult) -> dict[str, object]:
    """整套替换完成后的报告；备份只给文件名，不暴露服务器上的绝对路径。"""
    info = inspect_package(archive_path)
    backup = result.backup_path.name if result.backup_path is not None else ""
    report = {
        "mode": MODE_REPLACE,
        "slug": result.slug or slug,
        "is_dry_run": False,
        "source": info.summary(),
        "target_exists": backup != "",
        "backup_file": backup,
        "include_settings": True,
        "items": list(_sections(info).values()),
        "warnings": [NOTE_SETTINGS],
    }
    return _with_accounts(report, _accounts_result(info, result))


def run_replace(
    runtime: TenantRuntime,
    control_factory: sessionmaker[Session],
    archive_path: Path,
    slug: str,
    actor_id: int | None = None,
) -> dict[str, object]:
    """整套替换（调用方已完成二次确认）：沿用 restore 的备份与暂存切换逻辑。"""
    inspect_package(archive_path)
    result = import_tenant(
        runtime, control_factory, archive_path, slug, overwrite=True, actor_id=actor_id
    )
    return replace_report(archive_path, slug, result)
