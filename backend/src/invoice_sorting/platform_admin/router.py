"""平台运营后台路由汇总（前缀 /api/platform，全部仅限平台管理员）。"""

from typing import Any

from fastapi import APIRouter

from invoice_sorting.common.errors import ok
from invoice_sorting.control.deps import ControlSessionDep
from invoice_sorting.control.platform_deps import PLATFORM_ADMIN_ONLY
from invoice_sorting.platform_admin.license_router import router as license_router
from invoice_sorting.platform_admin.member_router import router as member_router
from invoice_sorting.platform_admin.plan_router import router as plan_router
from invoice_sorting.platform_admin.tenant_router import router as tenant_router
from invoice_sorting.platform_admin.usage import platform_totals

overview_router = APIRouter(prefix="/api/platform", tags=["平台概览"])


@overview_router.get("/overview", dependencies=PLATFORM_ADMIN_ONLY)
def read_overview(control: ControlSessionDep) -> dict[str, Any]:
    """平台概览统计；同时作为前端判断「当前账号是不是平台管理员」的探针。"""
    return ok(platform_totals(control))


router = APIRouter()
for included in (overview_router, tenant_router, member_router, plan_router, license_router):
    router.include_router(included)
