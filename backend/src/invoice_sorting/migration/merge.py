"""合并导入引擎（账本搬迁设计 3、4、7）：把搬迁包并入一个已有账本，已存在的跳过。

- `preview_merge`：dry-run，只读规划，返回报告，不写任何数据；
- `merge_import`：按同一规划执行，返回同结构报告。整体成功或整体回滚：
  业务库全部写入在一个事务里（分块 flush），新落盘的文件与文件夹逐一登记，
  失败时回滚事务、删除本次新建的文件、撤销控制库里的占位账号。
- `preview_import` / `run_import`：与网页导入的接缝约定（engine_bridge）一致，按 mode 分派，
  返回可直接序列化的字典；覆盖模式沿用 restore 的整套替换（备份 + 暂存切换）。
- 不执行包内任何设置覆盖：地区、买方抬头、认证、授权与日志配置一概不动（本来就不读 app_setting）。
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from sqlalchemy.orm import Session, sessionmaker

from invoice_sorting.common.errors import AppError
from invoice_sorting.config import DEFAULT_TENANT_NAME, DEFAULT_TENANT_SLUG
from invoice_sorting.control.repository import ensure_tenant, find_tenant, require_slug
from invoice_sorting.migration.merge_apply import (
    IdMaps,
    apply_batches,
    apply_catalog,
    apply_exports,
    apply_users,
)
from invoice_sorting.migration.merge_apply_records import ApplyContext, apply_records
from invoice_sorting.migration.merge_files import FileTracker, file_source, staging_dir
from invoice_sorting.migration.merge_plan import MergePlan, build_plan
from invoice_sorting.migration.package import (
    ImportRejectedError,
    PackageInfo,
    inspect_package,
    open_package_db,
)
from invoice_sorting.migration.placeholders import CreatedPlaceholder, remove_placeholders
from invoice_sorting.migration.replace_preview import MODE_REPLACE, preview_replace, run_replace
from invoice_sorting.migration.report import MergeReport
from invoice_sorting.tenancy.runtime import TenantContext, TenantRuntime

logger = logging.getLogger(__name__)

MSG_TARGET_MISSING = (
    "账套 {slug} 不存在：合并导入只能并入已有账套；"
    "要把搬迁包导入为新账套，请使用覆盖模式（replace）"
)
MSG_FAILED = "合并导入失败，已回滚到导入前的状态：{reason}"
MSG_FAILED_UNKNOWN = "内部错误（{kind}），详情见服务端日志"
WARN_LEGACY = "旧版搬迁包（没有 ledger.json），按整账套包处理，来源名称取自清单"
WARN_NOTHING = "包里的内容在本地都已存在，没有需要导入的数据"
WARN_CONFLICTS = "有 {count} 项与本地冲突，已保留本地内容，请查看明细"
WARN_FAILED = "有 {count} 项无法导入（包内数据缺失或不一致），请查看明细"
MODE_MERGE = "merge"
MODES = (MODE_MERGE, MODE_REPLACE)
MSG_MODE_INVALID = "导入模式只能是 merge（合并）或 replace（覆盖），收到：{mode}"


class ImportFailedError(AppError):
    """执行阶段失败：已整体回滚，本地账本与导入前一致。"""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=500)


@dataclass(frozen=True)
class _Target:
    context: TenantContext
    tenant_id: int | None  # 单租户老部署的 default 可能尚未登记到控制库


def preview_merge(
    runtime: TenantRuntime, control_factory: sessionmaker[Session], archive_path: Path, slug: str
) -> MergeReport:
    """预览：将新增/跳过/冲突的数量与明细。不写入业务库、控制库与文件库。"""
    info = inspect_package(archive_path)
    target = _resolve_target(runtime, control_factory, slug)
    with staging_dir(target.context.settings) as staging:
        with open_package_db(info, staging) as package_factory:
            with package_factory() as pkg, target.context.session_factory() as db:
                plan = build_plan(pkg, db, info)
    return _report(target.context.slug, info, plan, is_dry_run=True)


def merge_import(
    runtime: TenantRuntime, control_factory: sessionmaker[Session], archive_path: Path, slug: str
) -> MergeReport:
    """执行合并导入，返回与预览同结构的结果报告。"""
    info = inspect_package(archive_path)
    target = _resolve_target(runtime, control_factory, slug)
    tenant_id = target.tenant_id or _ensure_default_tenant(control_factory)
    settings = target.context.settings
    with staging_dir(settings) as staging, open_package_db(info, staging) as package_factory:
        with package_factory() as pkg, target.context.session_factory() as db:
            plan = build_plan(pkg, db, info)
            if not plan.is_empty:
                _execute(db, pkg, control_factory, tenant_id, target.context, info, plan, staging)
    report = _report(target.context.slug, info, plan, is_dry_run=False)
    logger.info("账套 %s 合并导入完成：新增 %s 项", target.context.slug, report.total_added)
    return report


def _resolve_target(
    runtime: TenantRuntime, control_factory: sessionmaker[Session], slug: str
) -> _Target:
    try:
        normalized = require_slug(slug)
    except AppError as error:
        raise ImportRejectedError(error.message) from error
    with control_factory() as control:
        tenant = find_tenant(control, normalized)
        tenant_id = tenant.id if tenant is not None else None
    is_legacy_default = normalized == DEFAULT_TENANT_SLUG and not runtime.base_settings.is_saas
    if tenant_id is None and not is_legacy_default:
        raise ImportRejectedError(MSG_TARGET_MISSING.format(slug=normalized), status_code=404)
    return _Target(context=runtime.get(normalized), tenant_id=tenant_id)


def _ensure_default_tenant(control_factory: sessionmaker[Session]) -> int:
    with control_factory() as control:
        tenant = ensure_tenant(control, DEFAULT_TENANT_SLUG, DEFAULT_TENANT_NAME)
        control.commit()
        return tenant.id


def _execute(  # noqa: PLR0913 - 执行阶段需要的全部句柄，集中在一处便于统一回滚
    db: Session,
    pkg: Session,
    control_factory: sessionmaker[Session],
    tenant_id: int,
    context: TenantContext,
    info: PackageInfo,
    plan: MergePlan,
    staging: Path,
) -> None:
    tracker = FileTracker(context.settings.library_dir)
    with control_factory() as control:
        try:
            with file_source(info, staging) as files:
                created = _apply(db, pkg, control, tenant_id, context, files, tracker, plan)
            control.commit()
        except BaseException as error:
            control.rollback()
            _undo(db, tracker, ())
            _raise_failure(error)
    try:
        db.commit()
    except BaseException as error:
        _undo(db, tracker, created, control_factory)
        _raise_failure(error)


def _apply(  # noqa: PLR0913
    db: Session,
    pkg: Session,
    control: Session,
    tenant_id: int,
    context: TenantContext,
    files,  # noqa: ANN001 - FileSource
    tracker: FileTracker,
    plan: MergePlan,
) -> tuple[CreatedPlaceholder, ...]:
    """按依赖顺序写入：人 → 分类与项目（及规则、记忆）→ 批次 → 记录与附件 → 生成记录。"""
    users, created = apply_users(control, db, tenant_id, plan.users)
    categories, projects = apply_catalog(db, pkg, plan.catalog)
    batches = apply_batches(db, pkg, plan.batches, users, projects)
    maps = IdMaps(users=users, categories=categories, projects=projects, batches=batches)
    ctx = ApplyContext(db, pkg, context.settings, files, tracker, maps)
    apply_records(ctx, plan.records)
    apply_exports(db, pkg, plan.batches, maps)
    return created


def _undo(
    db: Session,
    tracker: FileTracker,
    created: tuple[CreatedPlaceholder, ...],
    control_factory: sessionmaker[Session] | None = None,
) -> None:
    db.rollback()
    tracker.rollback()
    if control_factory is not None and created:
        remove_placeholders(control_factory, [item.account_id for item in created])


def _raise_failure(error: BaseException) -> NoReturn:
    """校验类错误原样抛出；其余统一包装成“已回滚”的导入失败，不泄露内部细节。"""
    if isinstance(error, ImportRejectedError) or not isinstance(error, Exception):
        raise error
    if isinstance(error, AppError):
        raise ImportFailedError(MSG_FAILED.format(reason=error.message)) from error
    logger.exception("合并导入失败，已回滚")
    reason = MSG_FAILED_UNKNOWN.format(kind=type(error).__name__)
    raise ImportFailedError(MSG_FAILED.format(reason=reason)) from error


def _report(slug: str, info: PackageInfo, plan: MergePlan, is_dry_run: bool) -> MergeReport:
    sections = plan.sections.values()
    conflicts = sum(section.conflicts for section in sections)
    failed = sum(section.failed for section in sections)
    warnings = [
        *([WARN_LEGACY] if info.is_legacy else []),
        *([WARN_NOTHING] if plan.is_empty else []),
        *([WARN_CONFLICTS.format(count=conflicts)] if conflicts else []),
        *([WARN_FAILED.format(count=failed)] if failed else []),
    ]
    return MergeReport(
        slug=slug,
        is_dry_run=is_dry_run,
        package=info.summary(),
        sections=plan.sections,
        warnings=tuple(warnings),
    )


def _require_mode(mode: str) -> str:
    if mode not in MODES:
        raise ImportRejectedError(MSG_MODE_INVALID.format(mode=mode))
    return mode


def preview_import(
    runtime: TenantRuntime,
    control_factory: sessionmaker[Session],
    archive_path: Path,
    slug: str,
    mode: str = MODE_MERGE,
) -> dict[str, object]:
    """预览（dry-run），不写入任何数据。返回 MergeReport.to_dict() 同形状的字典。"""
    if _require_mode(mode) == MODE_REPLACE:
        return preview_replace(runtime, control_factory, archive_path, slug)
    return preview_merge(runtime, control_factory, archive_path, slug).to_dict()


def run_import(
    runtime: TenantRuntime,
    control_factory: sessionmaker[Session],
    archive_path: Path,
    slug: str,
    mode: str = MODE_MERGE,
) -> dict[str, object]:
    """执行导入。覆盖模式不再追问：调用方须已完成二次确认（网页输账套名、命令行 --overwrite）"""
    if _require_mode(mode) == MODE_REPLACE:
        return run_replace(runtime, control_factory, archive_path, slug)
    return merge_import(runtime, control_factory, archive_path, slug).to_dict()
