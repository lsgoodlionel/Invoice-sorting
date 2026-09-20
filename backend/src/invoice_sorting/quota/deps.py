"""额度相关依赖：取出装配在应用上的额度服务。"""

from typing import Annotated

from fastapi import Depends, Request

from invoice_sorting.quota.guard import STATE_SERVICE_KEY, quota_service_of
from invoice_sorting.quota.service import QuotaService


def get_quota_service(request: Request) -> QuotaService:
    service = quota_service_of(request.app)
    if service is None:  # pragma: no cover - 应用启动时必定装配
        raise RuntimeError(f"应用未装配额度服务（app.state.{STATE_SERVICE_KEY}）")
    return service


QuotaServiceDep = Annotated[QuotaService, Depends(get_quota_service)]
