"""加成员前的细粒度额度校验。

写守卫豁免了 `/api/auth/*`（登录不能被只读挡住），而凭邀请码加入账套恰好走这个前缀，
因此这条公开入口必须自己校验一次：账套是否可写、成员数是否已达套餐上限。
只需要控制库即可完成，不涉及业务库与磁盘。
"""

from sqlalchemy.orm import Session

from invoice_sorting.common.errors import AppError
from invoice_sorting.config import Settings
from invoice_sorting.control.models import Tenant
from invoice_sorting.db.models import now
from invoice_sorting.quota.constants import KIND_USERS
from invoice_sorting.quota.plans import is_unlimited, limit_of, resolve_limits
from invoice_sorting.quota.state import exceeded_message, readonly_notice
from invoice_sorting.quota.usage import count_active_members

STATUS_CODE = 403


def ensure_member_capacity(settings: Settings, control: Session, tenant: Tenant) -> None:
    """成员数已满或账套只读时抛出 403；单账套部署不做限制。"""
    if not settings.is_saas:
        return
    notice = readonly_notice(tenant.status, tenant.expires_on, now().date())
    if notice.is_readonly:
        raise AppError(notice.message, status_code=STATUS_CODE)
    limits = resolve_limits(control, tenant)
    limit = limit_of(limits, KIND_USERS)
    if is_unlimited(limit):
        return
    used = count_active_members(control, tenant.id)
    if used >= limit:
        raise AppError(exceeded_message(limits, KIND_USERS, used), status_code=STATUS_CODE)
