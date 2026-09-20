"""应用入口：创建 FastAPI、挂载各模块路由与前端静态文件。"""

import argparse
import logging
import webbrowser
from collections.abc import Sequence
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from invoice_sorting.attachments.router import router as attachments_router
from invoice_sorting.auth.cli import reset_password
from invoice_sorting.auth.middleware import AuthMiddleware
from invoice_sorting.auth.ratelimit import LoginRateLimiter
from invoice_sorting.auth.router import router as auth_router
from invoice_sorting.auth.tenant_router import router as auth_tenant_router
from invoice_sorting.batches.router import router as batches_router
from invoice_sorting.checklist.router import router as checklist_router
from invoice_sorting.common.errors import install_error_handlers, ok
from invoice_sorting.config import DEFAULT_TENANT_NAME, DEFAULT_TENANT_SLUG, Settings
from invoice_sorting.control.database import (
    create_control_engine,
    init_control_db,
    make_control_session_factory,
)
from invoice_sorting.control.migrate import migrate_tenant_accounts
from invoice_sorting.control.repository import ensure_tenant
from invoice_sorting.expenses.reclassify_router import router as reclassify_router
from invoice_sorting.expenses.router import router as expenses_router
from invoice_sorting.importer.router import router as importer_router
from invoice_sorting.invites.router import router as invites_router
from invoice_sorting.licensing.deps import license_write_check
from invoice_sorting.licensing.guard import install_write_guards
from invoice_sorting.licensing.middleware import WriteGuardMiddleware
from invoice_sorting.licensing.platform_router import router as platform_license_router
from invoice_sorting.licensing.router import router as license_router
from invoice_sorting.licensing.scheduler import LicenseScheduler, interval_seconds
from invoice_sorting.licensing.service import LicenseService
from invoice_sorting.migration import cli as migration_cli
from invoice_sorting.migration.jobs import ExportJobStore
from invoice_sorting.migration.router import router as migration_router
from invoice_sorting.settings.router import router as settings_router
from invoice_sorting.stats.router import router as stats_router
from invoice_sorting.tenancy.runtime import TenantRuntime
from invoice_sorting.users.router import router as users_router
from invoice_sorting.users.sync import sync_tenant_mirror

logger = logging.getLogger("invoice_sorting")

DEFAULT_FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    control_engine = create_control_engine(settings)
    init_control_db(control_engine)
    control_factory = make_control_session_factory(control_engine)
    # 租户业务库首次加载时，按控制库的 membership 补齐用户镜像
    runtime = TenantRuntime(
        settings, on_open=lambda context: sync_tenant_mirror(control_factory, context)
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        watcher = _start_watcher(app, settings)
        scheduler = _start_license_scheduler(app, settings)
        yield
        if scheduler is not None:
            scheduler.stop()
        if watcher is not None:
            watcher.stop()
        runtime.close()
        control_engine.dispose()

    app = FastAPI(title="个人发票报销管理工具", lifespan=lifespan)
    app.state.settings = settings
    app.state.control_engine = control_engine
    app.state.control_session_factory = control_factory
    app.state.tenants = runtime
    app.state.login_limiter = LoginRateLimiter()
    app.state.export_jobs = ExportJobStore()
    # SaaS 模式不预置业务库：租户业务库在首次访问时按 slug 懒加载
    if not settings.is_saas:
        _prepare_single_tenant(app)
    _prepare_license(app, settings)
    install_error_handlers(app)
    # 认证在外层：未登录的写请求先得到 401，不会泄漏本机授权状态
    app.add_middleware(WriteGuardMiddleware)
    app.add_middleware(AuthMiddleware)

    for router in (
        auth_router,
        auth_tenant_router,
        invites_router,
        expenses_router,
        attachments_router,
        importer_router,
        checklist_router,
        batches_router,
        stats_router,
        settings_router,
        users_router,
        reclassify_router,
        migration_router,
        license_router,
        platform_license_router,
    ):
        app.include_router(router)

    @app.get("/api/health")
    def health() -> dict:
        return ok({"status": "up"})

    _mount_frontend(app, settings.frontend_dist or DEFAULT_FRONTEND_DIST)
    return app


def _prepare_single_tenant(app: FastAPI) -> None:
    """单租户：确保控制库中有 default 租户（绑定现有 data_dir），并迁移老数据。

    业务库仍在 data_dir 根目录；app.state.engine / session_factory 保持向后兼容。
    """
    runtime: TenantRuntime = app.state.tenants
    with app.state.control_session_factory() as control:
        tenant = ensure_tenant(control, DEFAULT_TENANT_SLUG, DEFAULT_TENANT_NAME)
        control.commit()
        tenant_id = tenant.id
    context = runtime.get(DEFAULT_TENANT_SLUG)
    app.state.engine = context.engine
    app.state.session_factory = context.session_factory
    with app.state.control_session_factory() as control:
        migrate_tenant_accounts(control, tenant_id, context.session_factory)
        control.commit()


def _prepare_license(app: FastAPI, settings: Settings) -> None:
    """装配私有化授权：读取本地状态（不联网）并登记写操作守卫。

    守卫是**可组合**的：后续批次（套餐额度、租户状态）用 guard.register_write_guard 追加原因。
    """
    service = LicenseService(settings, app.state.control_session_factory)
    service.start()
    app.state.license_service = service
    app.state.license_limiter = LoginRateLimiter()
    install_write_guards(app, (license_write_check,))


def _start_license_scheduler(app: FastAPI, settings: Settings) -> LicenseScheduler | None:
    """定时在线校验。未配置授权密钥或多租户模式下不启动，也不会发起任何网络请求。"""
    service: LicenseService = app.state.license_service
    if not service.is_enabled:
        return None
    scheduler = LicenseScheduler(service, interval_seconds(settings.license_check_interval_hours))
    scheduler.start()
    return scheduler


def _start_watcher(app: FastAPI, settings: Settings):
    """收件箱监听。SaaS 模式本批不启用：租户按需加载，多租户监听在后续批次随运营后台补齐。"""
    if not settings.watch_inbox:
        return None
    if settings.is_saas:
        logger.info("SaaS 模式暂不启用收件箱监听")
        return None
    try:
        from invoice_sorting.importer.watcher import start_inbox_watcher

        return start_inbox_watcher(app)
    except Exception:
        logger.exception("收件箱监听启动失败，已跳过")
        return None


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    index = dist / "index.html"
    if not index.exists():
        return
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str) -> FileResponse:
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="invoice-sorting", description="个人发票报销管理工具")
    commands = parser.add_subparsers(dest="command")
    reset = commands.add_parser(
        "reset-password", help="清除 admin（或指定用户）的密码与其全部会话，之后在网页重新设置"
    )
    reset.add_argument("--user", metavar="用户名", help="要清除密码的用户，默认 admin")
    _add_migration_commands(commands)
    return parser.parse_args(argv)


def _add_migration_commands(commands) -> None:  # noqa: ANN001 - argparse 的子命令容器
    """数据搬迁命令（设计 7）：导出与导入账套数据包。"""
    export = commands.add_parser(
        "export-tenant", help="导出账套数据包（数据库快照 + 文件库 + 资料包）"
    )
    export.add_argument("--slug", metavar="账套标识", help="要导出的账套，单租户部署可省略")
    export.add_argument("--out", metavar="输出文件", help="输出 zip 路径，省略时写入备份目录")
    export.add_argument("--no-packages", action="store_true", help="不导出资料包（可再次生成）")
    restore = commands.add_parser("import-tenant", help="把账套数据包导入为指定账套")
    restore.add_argument("--in", dest="archive", metavar="搬迁包", required=True, help="zip 路径")
    restore.add_argument("--slug", metavar="账套标识", required=True, help="导入到哪个账套")
    restore.add_argument(
        "--overwrite", action="store_true", help="覆盖已存在的账套（覆盖前自动备份）"
    )


def run(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.command == "reset-password":
        reset_password(Settings(), args.user)
        return
    if args.command == "export-tenant":
        migration_cli.run_export(Settings(), args.slug, args.out, args.no_packages)
        return
    if args.command == "import-tenant":
        migration_cli.run_import(Settings(), args.archive, args.slug, args.overwrite)
        return
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    app = create_app(settings)
    url = f"http://{settings.host}:{settings.port}"
    if settings.open_browser:
        webbrowser.open(url)
    uvicorn.run(app, host=settings.host, port=settings.port)
