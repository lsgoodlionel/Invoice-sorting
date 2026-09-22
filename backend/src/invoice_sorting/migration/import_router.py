"""网页导入接口（设计 5、7）：分片上传 → 合并校验与预览 → 确认导入 → 查询与取消。

- 账套侧 `/api/backup/imports*`：仅管理员，目标账套一律取自当前请求（子域名或登录会话），
  请求体里多出的字段（例如 slug）直接 422，不接受客户端指定别的账套；
- 平台侧 `/api/platform/tenants/{slug}/imports*`：仅平台管理员，可导入任意已开通账套，
  复用同一套实现；
- 两侧都是写操作，只读降级与账套停用时由写守卫统一拒绝（403）。
"""

from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from starlette.concurrency import run_in_threadpool

from invoice_sorting.auth.deps import ADMIN_ONLY, get_current_user
from invoice_sorting.common.errors import ok
from invoice_sorting.control.platform_deps import PLATFORM_ADMIN_ONLY
from invoice_sorting.migration import import_service as service
from invoice_sorting.migration.import_service import missing_parts, store_of
from invoice_sorting.migration.tenants import require_known_tenant, tenant_name
from invoice_sorting.migration.upload_files import received_parts
from invoice_sorting.migration.upload_store import (
    DEFAULT_PART_BYTES,
    STATUS_UPLOADING,
    UploadSession,
)
from invoice_sorting.tenancy.deps import get_tenant

SHA256_PATTERN = r"^[0-9a-fA-F]{64}$"
FILENAME_MAX = 255
CONFIRM_NAME_MAX = 100
ImportMode = Literal["merge", "replace"]

STATUS_MESSAGES = {
    "uploading": "等待上传分片",
    "ready": "账本包已校验，请查看预览后确认导入",
    "running": "正在导入，请稍候",
    "done": "导入完成",
}

tenant_router = APIRouter(prefix="/api/backup/imports", tags=["账本导入"])
platform_router = APIRouter(prefix="/api/platform/tenants/{slug}/imports", tags=["平台账本导入"])
router = APIRouter()


class CreateImportRequest(BaseModel):
    """登记上传：文件名仅用于展示，大小与整包 SHA-256 在完成时逐字节核对。"""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=FILENAME_MAX)
    size: int = Field(gt=0)
    part_size: int = DEFAULT_PART_BYTES
    sha256: str = Field(pattern=SHA256_PATTERN)


class CompleteImportRequest(BaseModel):
    """include_settings：合并时同时导入系统设置（以包为准）；覆盖模式本就整体替换，忽略此项。"""

    model_config = ConfigDict(extra="forbid")

    mode: ImportMode = "merge"
    include_settings: StrictBool = True


class ConfirmImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ImportMode = "merge"
    confirm_name: str = Field(default="", max_length=CONFIRM_NAME_MAX)
    include_settings: StrictBool = True


def session_payload(app: Any, session: UploadSession) -> dict[str, Any]:
    """会话状态；分片进度只在 uploading 阶段有意义，之后两个列表都为空。"""
    store = store_of(app)
    is_uploading = session.status == STATUS_UPLOADING
    report = session.report
    return {
        "upload_id": session.id,
        "slug": session.slug,
        "target_name": tenant_name(app, session.slug),
        "status": session.status,
        "mode": session.mode,
        "include_settings": session.include_settings,
        "message": session.error or STATUS_MESSAGES.get(session.status, ""),
        "error": session.error,
        "progress": None,
        "filename": session.filename,
        "size": session.total_size,
        "part_size": session.part_size,
        "part_count": session.part_count,
        "received_parts": list(
            received_parts(store.parts_dir(session), session.part_count) if is_uploading else ()
        ),
        "missing_parts": list(missing_parts(store, session) if is_uploading else ()),
        "backup_file": (report or {}).get("backup_file", ""),
        "report": report,
        "created_at": session.created_at.isoformat(),
        "expires_at": session.expires_at.isoformat(),
    }


def _preview_payload(app: Any, session: UploadSession) -> dict[str, Any]:
    """完成上传的返回：预览报告字段（items/source/warnings…）平铺在顶层，便于直接展示。"""
    return {**(session.report or {}), **session_payload(app, session)}


def _tenant_slug(request: Request) -> str:
    return get_tenant(request).slug


def _create(request: Request, slug: str, body: CreateImportRequest) -> dict[str, Any]:
    session = service.start_upload(
        request.app, slug, body.filename, body.size, body.part_size, body.sha256
    )
    return ok(session_payload(request.app, session))


async def _put_part(request: Request, slug: str, upload_id: str, index: int) -> dict[str, Any]:
    session = await service.receive_part(request.app, slug, upload_id, index, request.stream())
    return ok(await run_in_threadpool(session_payload, request.app, session))


def _actor_id(request: Request) -> int | None:
    """执行导入的账号：单账套覆盖恢复账号时，备份里没有他也不会被删除。"""
    user = get_current_user(request)
    return user.id if user is not None else None


def _complete(
    request: Request, slug: str, upload_id: str, body: CompleteImportRequest | None
) -> dict[str, Any]:
    options = body or CompleteImportRequest()
    session = service.complete_upload(
        request.app,
        slug,
        upload_id,
        options.mode,
        options.include_settings,
        actor_id=_actor_id(request),
    )
    return ok(_preview_payload(request.app, session))


def _confirm(
    request: Request,
    tasks: BackgroundTasks,
    slug: str,
    upload_id: str,
    body: ConfirmImportRequest,
) -> dict[str, Any]:
    app = request.app
    session = service.confirm_import(
        app,
        slug,
        upload_id,
        body.mode,
        body.confirm_name,
        body.include_settings,
        actor_id=_actor_id(request),
    )
    tasks.add_task(service.run_confirmed, app, slug, upload_id)
    return ok(session_payload(app, session))


def _status(request: Request, slug: str, upload_id: str) -> dict[str, Any]:
    session = store_of(request.app).require(slug, upload_id)
    return ok(session_payload(request.app, session))


def _cancel(request: Request, slug: str, upload_id: str) -> dict[str, Any]:
    service.cancel_upload(request.app, slug, upload_id)
    return ok(None)


# ---- 账套侧：目标账套取自当前请求 ----


@tenant_router.post("", dependencies=ADMIN_ONLY)
def create_tenant_import(request: Request, body: CreateImportRequest) -> dict[str, Any]:
    return _create(request, _tenant_slug(request), body)


@tenant_router.put("/{upload_id}/parts/{index}", dependencies=ADMIN_ONLY)
async def put_tenant_part(upload_id: str, index: int, request: Request) -> dict[str, Any]:
    slug = await run_in_threadpool(_tenant_slug, request)
    return await _put_part(request, slug, upload_id, index)


@tenant_router.post("/{upload_id}/complete", dependencies=ADMIN_ONLY)
def complete_tenant_import(
    upload_id: str, request: Request, body: CompleteImportRequest | None = None
) -> dict[str, Any]:
    return _complete(request, _tenant_slug(request), upload_id, body)


@tenant_router.post("/{upload_id}/confirm", dependencies=ADMIN_ONLY)
def confirm_tenant_import(
    upload_id: str, request: Request, tasks: BackgroundTasks, body: ConfirmImportRequest
) -> dict[str, Any]:
    return _confirm(request, tasks, _tenant_slug(request), upload_id, body)


@tenant_router.get("/{upload_id}/status", dependencies=ADMIN_ONLY)
def tenant_import_status(upload_id: str, request: Request) -> dict[str, Any]:
    return _status(request, _tenant_slug(request), upload_id)


@tenant_router.delete("/{upload_id}", dependencies=ADMIN_ONLY)
def cancel_tenant_import(upload_id: str, request: Request) -> dict[str, Any]:
    return _cancel(request, _tenant_slug(request), upload_id)


# ---- 平台侧：平台管理员指定任意已开通账套 ----


@platform_router.post("", dependencies=PLATFORM_ADMIN_ONLY)
def create_platform_import(
    slug: str, request: Request, body: CreateImportRequest
) -> dict[str, Any]:
    return _create(request, require_known_tenant(request.app, slug), body)


@platform_router.put("/{upload_id}/parts/{index}", dependencies=PLATFORM_ADMIN_ONLY)
async def put_platform_part(
    slug: str, upload_id: str, index: int, request: Request
) -> dict[str, Any]:
    normalized = await run_in_threadpool(require_known_tenant, request.app, slug)
    return await _put_part(request, normalized, upload_id, index)


@platform_router.post("/{upload_id}/complete", dependencies=PLATFORM_ADMIN_ONLY)
def complete_platform_import(
    slug: str, upload_id: str, request: Request, body: CompleteImportRequest | None = None
) -> dict[str, Any]:
    return _complete(request, require_known_tenant(request.app, slug), upload_id, body)


@platform_router.post("/{upload_id}/confirm", dependencies=PLATFORM_ADMIN_ONLY)
def confirm_platform_import(
    slug: str,
    upload_id: str,
    request: Request,
    tasks: BackgroundTasks,
    body: ConfirmImportRequest,
) -> dict[str, Any]:
    normalized = require_known_tenant(request.app, slug)
    return _confirm(request, tasks, normalized, upload_id, body)


@platform_router.get("/{upload_id}/status", dependencies=PLATFORM_ADMIN_ONLY)
def platform_import_status(slug: str, upload_id: str, request: Request) -> dict[str, Any]:
    return _status(request, require_known_tenant(request.app, slug), upload_id)


@platform_router.delete("/{upload_id}", dependencies=PLATFORM_ADMIN_ONLY)
def cancel_platform_import(slug: str, upload_id: str, request: Request) -> dict[str, Any]:
    return _cancel(request, require_known_tenant(request.app, slug), upload_id)


router.include_router(tenant_router)
router.include_router(platform_router)
