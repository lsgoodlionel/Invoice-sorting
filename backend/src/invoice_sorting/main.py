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

from invoice_sorting.attachments.file_keys import backfill_file_keys
from invoice_sorting.attachments.router import router as attachments_router
from invoice_sorting.auth.cli import reset_password
from invoice_sorting.auth.middleware import AuthMiddleware
from invoice_sorting.auth.migrate import migrate_users
from invoice_sorting.auth.ratelimit import LoginRateLimiter
from invoice_sorting.auth.router import router as auth_router
from invoice_sorting.batches.router import router as batches_router
from invoice_sorting.checklist.router import router as checklist_router
from invoice_sorting.common.errors import install_error_handlers, ok
from invoice_sorting.config import Settings
from invoice_sorting.db.seed import (
    reset_polluted_memory,
    seed_defaults,
    sync_default_keywords,
    sync_default_rules,
)
from invoice_sorting.db.session import create_db_engine, init_db, make_session_factory
from invoice_sorting.expenses.reclassify_router import router as reclassify_router
from invoice_sorting.expenses.router import router as expenses_router
from invoice_sorting.importer.router import router as importer_router
from invoice_sorting.settings.router import router as settings_router
from invoice_sorting.stats.router import router as stats_router
from invoice_sorting.users.router import router as users_router

logger = logging.getLogger("invoice_sorting")

DEFAULT_FRONTEND_DIST = Path(__file__).resolve().parents[3] / "frontend" / "dist"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.ensure_dirs()
    engine = create_db_engine(f"sqlite:///{settings.db_path}")
    init_db(engine)
    session_factory = make_session_factory(engine)
    with session_factory() as session:
        seed_defaults(session)
        sync_default_keywords(session)
        sync_default_rules(session)
        reset_polluted_memory(session)
        backfill_file_keys(session)
        migrate_users(session)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        watcher = None
        if settings.watch_inbox:
            try:
                from invoice_sorting.importer.watcher import start_inbox_watcher

                watcher = start_inbox_watcher(app)
            except Exception:
                logger.exception("收件箱监听启动失败，已跳过")
        yield
        if watcher is not None:
            watcher.stop()
        engine.dispose()

    app = FastAPI(title="个人发票报销管理工具", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.login_limiter = LoginRateLimiter()
    install_error_handlers(app)
    app.add_middleware(AuthMiddleware)

    for router in (
        auth_router,
        expenses_router,
        attachments_router,
        importer_router,
        checklist_router,
        batches_router,
        stats_router,
        settings_router,
        users_router,
        reclassify_router,
    ):
        app.include_router(router)

    @app.get("/api/health")
    def health() -> dict:
        return ok({"status": "up"})

    _mount_frontend(app, settings.frontend_dist or DEFAULT_FRONTEND_DIST)
    return app


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
    return parser.parse_args(argv)


def run(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.command == "reset-password":
        reset_password(Settings(), args.user)
        return
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    app = create_app(settings)
    url = f"http://{settings.host}:{settings.port}"
    if settings.open_browser:
        webbrowser.open(url)
    uvicorn.run(app, host=settings.host, port=settings.port)
