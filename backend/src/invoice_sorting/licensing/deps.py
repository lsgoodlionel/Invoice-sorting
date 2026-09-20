"""授权相关依赖与写操作原因来源。"""

from typing import Annotated, Any

from fastapi import Depends, Request

from invoice_sorting.licensing.constants import BLOCK_CODE_LICENSE
from invoice_sorting.licensing.guard import WriteBlock
from invoice_sorting.licensing.service import LicenseService

STATE_SERVICE_KEY = "license_service"


def get_license_service(request: Request) -> LicenseService:
    return getattr(request.app.state, STATE_SERVICE_KEY)


def license_write_check(conn: Any) -> WriteBlock | None:
    """授权只读时拒绝写操作；未装配授权服务（理论上不会发生）时放行。"""
    service = getattr(conn.scope["app"].state, STATE_SERVICE_KEY, None)
    if service is None:
        return None
    status = service.status()
    if not status.is_readonly:
        return None
    return WriteBlock(code=BLOCK_CODE_LICENSE, message=status.message)


LicenseServiceDep = Annotated[LicenseService, Depends(get_license_service)]
