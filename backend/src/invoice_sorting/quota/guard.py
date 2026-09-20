"""额度守卫：注册到 licensing.guard 的**唯一**写操作拦截入口，不另加中间件。

执行顺序由注册顺序决定（授权守卫在前，额度守卫在后），先命中先返回。
GET/HEAD、登录、授权、备份与导出由 licensing.guard 统一豁免，这里不重复判断。
"""

import logging
from typing import Any

from invoice_sorting.control.repository import find_tenant
from invoice_sorting.licensing.guard import WriteBlock
from invoice_sorting.quota.rules import checks_for, is_quota_exempt
from invoice_sorting.quota.service import QuotaService
from invoice_sorting.tenancy.deps import tenant_for_connection

logger = logging.getLogger(__name__)

STATE_SERVICE_KEY = "quota_service"


def quota_service_of(app: Any) -> QuotaService | None:
    return getattr(app.state, STATE_SERVICE_KEY, None)


def quota_write_check(conn: Any) -> WriteBlock | None:
    """租户停用/到期或某项额度已满时拒绝写操作；单账套部署直接放行。"""
    app = conn.scope["app"]
    service = quota_service_of(app)
    if service is None or not service.is_enforced:
        return None
    path = conn.scope.get("path", "")
    if is_quota_exempt(path):
        return None
    context = tenant_for_connection(app, conn)
    kinds = checks_for(conn.scope.get("method", ""), path)
    with app.state.control_session_factory() as control:
        tenant = find_tenant(control, context.slug)
        if tenant is None:  # 租户不存在由租户解析报错，这里不重复拦截
            return None
        return service.block(control, tenant, context, kinds)
