"""命令行搬迁（设计 7）：export-tenant 导出、import-tenant 导入。

两个命令都不依赖运行中的服务：自行打开控制库与租户运行时，用完即释放连接。
"""

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from invoice_sorting.common.errors import AppError
from invoice_sorting.config import DEFAULT_TENANT_NAME, DEFAULT_TENANT_SLUG, Settings
from invoice_sorting.control.database import (
    create_control_engine,
    init_control_db,
    make_control_session_factory,
)
from invoice_sorting.control.repository import find_tenant, require_slug
from invoice_sorting.db.models import now
from invoice_sorting.migration.export import export_filename, export_tenant
from invoice_sorting.migration.jobs import exports_dir
from invoice_sorting.migration.restore import import_tenant
from invoice_sorting.tenancy.runtime import TenantRuntime

EXIT_FAILED = 1
MSG_TENANT_UNKNOWN = "账套不存在：{slug}"
MSG_TENANT_EMPTY = "账套 {slug} 还没有数据（找不到 {path}），无需导出"


@dataclass(frozen=True)
class _Workspace:
    """一次命令执行期间的控制库与租户运行时。"""

    settings: Settings
    control: sessionmaker[Session]
    runtime: TenantRuntime


@contextmanager
def _workspace(settings: Settings) -> Iterator[_Workspace]:
    engine = create_control_engine(settings)
    init_control_db(engine)
    runtime = TenantRuntime(settings)
    try:
        yield _Workspace(settings, make_control_session_factory(engine), runtime)
    finally:
        runtime.close()
        engine.dispose()


def _fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(EXIT_FAILED)


def _tenant_name(space: _Workspace, slug: str) -> str:
    """取账套名称；单租户的 default 允许没有控制库记录（老部署首次使用命令行）。"""
    with space.control() as control:
        tenant = find_tenant(control, slug)
    if tenant is not None:
        return tenant.name
    if slug == DEFAULT_TENANT_SLUG and not space.settings.is_saas:
        return DEFAULT_TENANT_NAME
    _fail(MSG_TENANT_UNKNOWN.format(slug=slug))
    return ""  # pragma: no cover - _fail 已退出


def _resolve_out(settings: Settings, slug: str, out: str | None) -> Path:
    if out:
        return Path(out).expanduser()
    return exports_dir(settings) / export_filename(slug, now())


def export_command(
    settings: Settings, slug: str | None, out: str | None, include_packages: bool = True
) -> None:
    """导出账套数据包；单租户部署可省略 --slug。"""
    normalized = require_slug(slug or DEFAULT_TENANT_SLUG)
    with _workspace(settings) as space:
        name = _tenant_name(space, normalized)
        target_settings = settings.for_tenant(normalized)
        if not target_settings.db_path.exists():
            _fail(MSG_TENANT_EMPTY.format(slug=normalized, path=target_settings.db_path))
        result = export_tenant(
            space.runtime.get(normalized),
            _resolve_out(settings, normalized, out),
            tenant_name=name,
            include_packages=include_packages,
        )
    print(f"已导出账套 {normalized}（{name}）→ {result.path}")
    print(f"文件 {result.file_count} 个，合计 {result.total_bytes} 字节")


def import_command(settings: Settings, archive: str, slug: str, overwrite: bool = False) -> None:
    """导入搬迁包为指定账套；目标已存在时需显式 --overwrite（会先备份）。"""
    with _workspace(settings) as space:
        result = import_tenant(
            space.runtime, space.control, Path(archive).expanduser(), slug, overwrite=overwrite
        )
    if result.backup_path is not None:
        print(f"覆盖前已备份现有数据 → {result.backup_path}")
    print(f"已导入账套 {result.slug}（#{result.tenant_id}）")
    print(f"文件 {result.file_count} 个，合计 {result.total_bytes} 字节")
    if not result.accounts.is_empty:
        report = result.accounts
        print(f"已迁移账号 {report.accounts} 个、成员关系 {report.memberships} 条")


def run_export(settings: Settings, slug: str | None, out: str | None, no_packages: bool) -> None:
    """main 的调度入口：把业务错误转成明确的中文提示与非 0 退出码。"""
    try:
        export_command(settings, slug, out, include_packages=not no_packages)
    except AppError as error:
        _fail(error.message)


def run_import(settings: Settings, archive: str, slug: str, overwrite: bool) -> None:
    try:
        import_command(settings, archive, slug, overwrite=overwrite)
    except AppError as error:
        _fail(error.message)
