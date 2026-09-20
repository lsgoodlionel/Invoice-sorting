"""授权状态接口：所有登录用户可查看状态，管理员可手动复检。"""

from typing import Any

from fastapi import APIRouter

from invoice_sorting.auth.deps import ADMIN_ONLY
from invoice_sorting.common.errors import ok
from invoice_sorting.licensing.constants import LICENSE_PREFIX
from invoice_sorting.licensing.deps import LicenseServiceDep
from invoice_sorting.licensing.serializers import serialize_status

router = APIRouter(prefix=LICENSE_PREFIX, tags=["授权"])


@router.get("/status")
def read_status(service: LicenseServiceDep) -> dict[str, Any]:
    """当前授权状态；前端据此显示顶部提示条。"""
    return ok(serialize_status(service.status()))


@router.post("/recheck", dependencies=ADMIN_ONLY)
def recheck(service: LicenseServiceDep) -> dict[str, Any]:
    """立即向授权服务校验一次（有频率限制）。"""
    return ok(serialize_status(service.recheck()))
