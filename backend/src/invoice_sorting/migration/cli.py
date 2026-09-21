"""命令行搬迁（设计 7、账本搬迁设计 6）：export-tenant 导出、import-tenant 导入（合并/覆盖/预览）。

两个命令都不依赖运行中的服务：自行打开控制库与租户运行时，用完即释放连接。
"""

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from invoice_sorting.common.errors import AppError, ConflictError
from invoice_sorting.config import DEFAULT_TENANT_NAME, DEFAULT_TENANT_SLUG, Settings
from invoice_sorting.control.database import (
    create_control_engine,
    init_control_db,
    make_control_session_factory,
)
from invoice_sorting.control.repository import find_tenant, require_slug
from invoice_sorting.db.models import now
from invoice_sorting.migration import merge as engine
from invoice_sorting.migration.cli_report import print_report
from invoice_sorting.migration.export import export_filename, export_tenant
from invoice_sorting.migration.jobs import exports_dir
from invoice_sorting.migration.merge import MODE_MERGE
from invoice_sorting.migration.package import ImportRejectedError, inspect_package
from invoice_sorting.migration.replace_preview import MODE_REPLACE, replace_report
from invoice_sorting.migration.restore import import_tenant
from invoice_sorting.tenancy.runtime import TenantRuntime

EXIT_FAILED = 1  # 导出失败 / 导入执行失败（已回滚）
EXIT_INVALID = 2  # 导入校验失败：包不合法、版本过新、目标账套不可用、参数冲突
MSG_OVERWRITE_MERGE = "--overwrite 只用于 --mode replace（整套替换），合并导入不会覆盖任何已有数据"
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


def _fail(message: str, code: int = EXIT_FAILED) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


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


def _resolve_mode(mode: str | None, overwrite: bool) -> str:
    """--mode 默认 merge；只给 --overwrite 视为旧写法的整套替换。"""
    resolved = mode or (MODE_REPLACE if overwrite else MODE_MERGE)
    if resolved == MODE_MERGE and overwrite:
        raise ImportRejectedError(MSG_OVERWRITE_MERGE)
    return resolved


def _replace(space: _Workspace, archive: Path, slug: str, overwrite: bool) -> dict:
    """整套替换：目标已存在时必须 --overwrite（执行前自动整包备份）。"""
    try:
        imported = import_tenant(space.runtime, space.control, archive, slug, overwrite=overwrite)
    except ConflictError as error:
        raise ImportRejectedError(error.message, status_code=error.status_code) from error
    return replace_report(archive, slug, imported)


def import_command(  # noqa: PLR0913 - 与命令行参数一一对应
    settings: Settings,
    archive: str,
    slug: str | None,
    mode: str | None = None,
    dry_run: bool = False,
    overwrite: bool = False,
) -> None:
    """导入搬迁包：默认合并到已有账套；--mode replace 整套替换；--dry-run 只预览。"""
    resolved = _resolve_mode(mode, overwrite)
    target = slug or DEFAULT_TENANT_SLUG
    path = Path(archive).expanduser()
    inspect_package(path)  # 先做只读体检：包不合法时以“校验失败”退出，不碰任何数据
    with _workspace(settings) as space:
        args = (space.runtime, space.control, path, target)
        if dry_run:
            report = engine.preview_import(*args, resolved)
        elif resolved == MODE_REPLACE:
            report = _replace(space, path, target, overwrite)
        else:
            report = engine.run_import(*args, resolved)
    print_report(report)


def run_export(settings: Settings, slug: str | None, out: str | None, no_packages: bool) -> None:
    """main 的调度入口：把业务错误转成明确的中文提示与非 0 退出码。"""
    try:
        export_command(settings, slug, out, include_packages=not no_packages)
    except AppError as error:
        _fail(error.message)


def run_import(  # noqa: PLR0913 - 与命令行参数一一对应
    settings: Settings,
    archive: str,
    slug: str | None,
    mode: str | None = None,
    dry_run: bool = False,
    overwrite: bool = False,
) -> None:
    """退出码：0 成功；2 校验失败（包不合法、版本过新、目标不可用），未写入任何数据；
    1 导入失败（已回滚到导入前的状态）。"""
    try:
        import_command(settings, archive, slug, mode, dry_run, overwrite)
    except ImportRejectedError as error:
        _fail(error.message, EXIT_INVALID)
    except AppError as error:
        _fail(error.message)
