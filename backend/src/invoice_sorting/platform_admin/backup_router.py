"""平台数据库备份接口（仅 SaaS、仅平台管理员）：生成、列表、下载。

单账套部署没有独立的“平台”，这三个接口一律 404；单账套的数据带走请用账本备份。
"""

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from invoice_sorting.common.errors import NotFoundError, ok
from invoice_sorting.control.platform_deps import PLATFORM_ADMIN_ONLY
from invoice_sorting.platform_admin.backups import (
    NOTICE,
    WHAT_BACKUP,
    create_backup,
    list_backups,
    resolve_backup,
)

SQLITE_MEDIA_TYPE = "application/vnd.sqlite3"

router = APIRouter(prefix="/api/platform/backups", tags=["平台数据库备份"])


def _require_saas(request: Request) -> None:
    if not request.app.state.settings.is_saas:
        raise NotFoundError(WHAT_BACKUP)


@router.post("", dependencies=PLATFORM_ADMIN_ONLY)
def start_platform_backup(request: Request) -> dict[str, Any]:
    _require_saas(request)
    app = request.app
    backup = create_backup(app.state.settings, app.state.control_engine)
    return ok({**backup.as_dict(), "notice": NOTICE})


@router.get("", dependencies=PLATFORM_ADMIN_ONLY)
def read_platform_backups(request: Request) -> dict[str, Any]:
    _require_saas(request)
    items = [backup.as_dict() for backup in list_backups(request.app.state.settings)]
    return ok({"items": items, "notice": NOTICE})


@router.get("/{name}", dependencies=PLATFORM_ADMIN_ONLY)
def download_platform_backup(name: str, request: Request) -> FileResponse:
    _require_saas(request)
    path = resolve_backup(request.app.state.settings, name)
    return FileResponse(path, media_type=SQLITE_MEDIA_TYPE, filename=path.name)
