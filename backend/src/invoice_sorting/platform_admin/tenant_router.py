"""账套管理 API（仅平台管理员）：列表、开通、修改、停用恢复与关闭。

停用或关闭后立刻驱逐该账套的运行时，释放数据库连接（设计 5）。
"""

from typing import Any

from fastapi import APIRouter, Query, Request

from invoice_sorting.common.errors import ok
from invoice_sorting.control.deps import ControlSessionDep
from invoice_sorting.control.platform_deps import PLATFORM_ADMIN_ONLY
from invoice_sorting.platform_admin.members import mirror_member
from invoice_sorting.platform_admin.schemas import TenantCreate, TenantUpdate
from invoice_sorting.platform_admin.serializers import serialize_invite, serialize_tenant
from invoice_sorting.platform_admin.tenants import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    OpenResult,
    TenantView,
    describe,
    is_runnable,
    list_tenants,
    open_tenant,
    require_tenant,
    update_tenant,
)
from invoice_sorting.users.serializers import serialize_member

router = APIRouter(prefix="/api/platform", tags=["平台账套"], dependencies=PLATFORM_ADMIN_ONLY)

SEARCH_MAX = 50


def _view(item: TenantView) -> dict[str, Any]:
    return serialize_tenant(item.tenant, item.plan, item.member_count, item.usage)


def _release(request: Request, slug: str) -> None:
    """账套不再对外服务时释放它的连接池（已借出的连接归还时才真正关闭）。"""
    request.app.state.tenants.evict(slug)


def _opened(result: OpenResult, view: TenantView) -> dict[str, Any]:
    return {
        **_view(view),
        "admin": serialize_member(result.member) if result.member is not None else None,
        "invite": serialize_invite(result.invite) if result.invite is not None else None,
    }


@router.get("/tenants")
def read_tenants(
    control: ControlSessionDep,
    q: str = Query("", max_length=SEARCH_MAX),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
) -> dict[str, Any]:
    """账套列表：支持按标识或名称搜索，按开通时间倒序分页。"""
    result = list_tenants(control, q, page, page_size)
    return ok(
        {
            "items": [_view(item) for item in result.items],
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
        }
    )


@router.post("/tenants")
def post_tenant(body: TenantCreate, request: Request, control: ControlSessionDep) -> dict[str, Any]:
    """开通账套：可同时开通首个管理员，或签发一张管理员邀请码。"""
    result = open_tenant(control, body)
    payload = _opened(result, describe(control, result.tenant))
    slug = result.tenant.slug
    control.commit()
    if result.member is not None:
        mirror_member(request.app, slug, result.member)
    return ok(payload)


@router.get("/tenants/{slug}")
def read_tenant(slug: str, control: ControlSessionDep) -> dict[str, Any]:
    return ok(_view(describe(control, require_tenant(control, slug))))


@router.patch("/tenants/{slug}")
def patch_tenant(
    slug: str, body: TenantUpdate, request: Request, control: ControlSessionDep
) -> dict[str, Any]:
    """改名、改套餐、改到期日、停用/恢复/关闭。"""
    tenant = update_tenant(control, require_tenant(control, slug), body)
    payload = _view(describe(control, tenant))
    should_release = not is_runnable(tenant)
    control.commit()
    if should_release:
        _release(request, slug)
    return ok(payload)
