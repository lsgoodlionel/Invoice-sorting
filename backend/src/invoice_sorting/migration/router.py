"""数据搬迁接口（设计 7）：后台生成搬迁包 + 任务状态查询 + 下载。

- 平台侧 `/api/platform/tenants/{slug}/export*`：运营后台导出任意账套（批次四接入按钮）。
- 私有化侧 `/api/backup/export-tenant*`：管理员导出自己所在账套，与现有 `/api/backup` 同风格。

导出是耗时操作，POST 只登记任务并立即返回任务号与下载地址，打包在后台线程进行。
导入不提供接口：搬迁包通常很大，统一走 `invoice-sorting import-tenant` 命令行。
"""

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from invoice_sorting.auth.deps import ADMIN_ONLY
from invoice_sorting.common.errors import AppError, NotFoundError, ok
from invoice_sorting.config import DEFAULT_TENANT_SLUG
from invoice_sorting.control.platform_deps import PLATFORM_ADMIN_ONLY
from invoice_sorting.control.repository import find_tenant, require_slug
from invoice_sorting.db.models import now
from invoice_sorting.migration.export import export_filename, export_tenant
from invoice_sorting.migration.jobs import (
    ExportJob,
    ExportJobStore,
    exports_dir,
    prune_exports,
    require_download,
)
from invoice_sorting.tenancy.deps import get_tenant, load_tenant

logger = logging.getLogger(__name__)

ZIP_MEDIA_TYPE = "application/zip"
WHAT_TENANT = "账套"
MSG_EXPORT_FAILED = "导出失败，请查看服务端日志"

platform_router = APIRouter(prefix="/api/platform", tags=["平台搬迁"])
tenant_router = APIRouter(prefix="/api/backup", tags=["数据搬迁"])
router = APIRouter()


class ExportRequest(BaseModel):
    """导出选项；资料包可再生成，导出时可以跳过以减小体积。"""

    include_packages: bool = True


def _job_store(app: Any) -> ExportJobStore:
    return app.state.export_jobs


def _tenant_name(app: Any, slug: str) -> str:
    with app.state.control_session_factory() as control:
        tenant = find_tenant(control, slug)
        return tenant.name if tenant is not None else slug


def _require_known_tenant(app: Any, slug: str) -> str:
    """校验 slug 形态并确认账套已开通，避免导出时误建一个空账套。"""
    normalized = require_slug(slug)
    if not app.state.settings.is_saas and normalized != DEFAULT_TENANT_SLUG:
        raise NotFoundError(WHAT_TENANT)
    with app.state.control_session_factory() as control:
        if find_tenant(control, normalized) is None:
            raise NotFoundError(WHAT_TENANT)
    return normalized


def _payload(job: ExportJob, download_url: str) -> dict[str, Any]:
    return ok(
        {
            "job": job.id,
            "slug": job.slug,
            "status": job.status,
            "file": job.filename,
            "size": job.size,
            "file_count": job.file_count,
            "error": job.error,
            "download_url": download_url,
        }
    )


JOB_TOKEN_CHARS = 8


def _run_export(app: Any, job_id: str, slug: str, include_packages: bool) -> None:
    """后台线程：生成搬迁包并更新任务状态；失败只记日志，不影响其他请求。"""
    store = _job_store(app)
    try:
        directory = exports_dir(app.state.settings)
        result = export_tenant(
            load_tenant(app, slug),
            directory / export_filename(slug, now(), job_id[:JOB_TOKEN_CHARS]),
            tenant_name=_tenant_name(app, slug),
            include_packages=include_packages,
        )
        store.finish(job_id, result.path, result.file_count)
        prune_exports(directory)
    except Exception as error:  # 后台任务必须兜住所有异常，否则任务永远停在 running
        logger.exception("账套 %s 导出失败", slug)
        store.fail(job_id, error.message if isinstance(error, AppError) else MSG_EXPORT_FAILED)


def _start(app: Any, tasks: BackgroundTasks, slug: str, body: ExportRequest | None) -> ExportJob:
    options = body or ExportRequest()
    job = _job_store(app).create(slug)
    tasks.add_task(_run_export, app, job.id, slug, options.include_packages)
    return job


def _download(app: Any, slug: str, job_id: str) -> FileResponse:
    path = require_download(_job_store(app).require(job_id, slug))
    return FileResponse(path, media_type=ZIP_MEDIA_TYPE, filename=path.name)


def _platform_url(slug: str, job_id: str) -> str:
    return f"/api/platform/tenants/{slug}/export/{job_id}"


def _tenant_url(job_id: str) -> str:
    return f"/api/backup/export-tenant/{job_id}"


@platform_router.post("/tenants/{slug}/export", dependencies=PLATFORM_ADMIN_ONLY)
def start_platform_export(
    slug: str, request: Request, tasks: BackgroundTasks, body: ExportRequest | None = None
) -> dict[str, Any]:
    normalized = _require_known_tenant(request.app, slug)
    job = _start(request.app, tasks, normalized, body)
    return _payload(job, _platform_url(normalized, job.id))


@platform_router.get("/tenants/{slug}/export/{job_id}/status", dependencies=PLATFORM_ADMIN_ONLY)
def platform_export_status(slug: str, job_id: str, request: Request) -> dict[str, Any]:
    normalized = require_slug(slug)
    job = _job_store(request.app).require(job_id, normalized)
    return _payload(job, _platform_url(normalized, job.id))


@platform_router.get("/tenants/{slug}/export/{job_id}", dependencies=PLATFORM_ADMIN_ONLY)
def download_platform_export(slug: str, job_id: str, request: Request) -> FileResponse:
    return _download(request.app, require_slug(slug), job_id)


@tenant_router.post("/export-tenant", dependencies=ADMIN_ONLY)
def start_tenant_export(
    request: Request, tasks: BackgroundTasks, body: ExportRequest | None = None
) -> dict[str, Any]:
    job = _start(request.app, tasks, get_tenant(request).slug, body)
    return _payload(job, _tenant_url(job.id))


@tenant_router.get("/export-tenant/{job_id}/status", dependencies=ADMIN_ONLY)
def tenant_export_status(job_id: str, request: Request) -> dict[str, Any]:
    job = _job_store(request.app).require(job_id, get_tenant(request).slug)
    return _payload(job, _tenant_url(job.id))


@tenant_router.get("/export-tenant/{job_id}", dependencies=ADMIN_ONLY)
def download_tenant_export(job_id: str, request: Request) -> FileResponse:
    return _download(request.app, get_tenant(request).slug, job_id)


router.include_router(platform_router)
router.include_router(tenant_router)
