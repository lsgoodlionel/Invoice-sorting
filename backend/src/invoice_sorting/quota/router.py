"""额度接口：当前账套的套餐、各项上限与用量、是否只读及原因。

所有登录用户都能查看（界面据此提示“还能新建多少条”“空间快满了”）。
单账套私有化部署返回 `enforced: false`，界面不应显示任何上限。
"""

from typing import Any

from fastapi import APIRouter, Request

from invoice_sorting.common.errors import ok
from invoice_sorting.control.deps import ControlSessionDep, require_tenant_row
from invoice_sorting.quota.constants import QUOTA_PATH
from invoice_sorting.quota.deps import QuotaServiceDep
from invoice_sorting.quota.serializers import serialize_report
from invoice_sorting.quota.state import QuotaReport
from invoice_sorting.tenancy.deps import get_tenant

router = APIRouter(prefix=QUOTA_PATH, tags=["套餐与额度"])


@router.get("")
def read_quota(
    request: Request, control: ControlSessionDep, service: QuotaServiceDep
) -> dict[str, Any]:
    today = service.today
    if not service.is_enforced:
        return ok(serialize_report(QuotaReport(is_enforced=False), today))
    context = get_tenant(request)
    tenant = require_tenant_row(control, context.slug)
    return ok(serialize_report(service.report(control, tenant, context), today))
