"""额度服务：把套餐、用量与租户状态组合成“能不能写”和“额度页面看什么”。

单账套私有化部署（deployment_mode=single）**完全不启用**：没有套餐概念，
不做任何统计与拦截，界面上也不显示上限。
"""

import logging
from collections.abc import Callable
from datetime import date, datetime

from sqlalchemy.orm import Session

from invoice_sorting.config import Settings
from invoice_sorting.control.models import Tenant
from invoice_sorting.db.models import now
from invoice_sorting.licensing.guard import WriteBlock
from invoice_sorting.quota.constants import (
    BLOCK_CODE_QUOTA,
    BLOCK_CODE_READONLY,
    KIND_EXPENSES,
    KIND_STORAGE,
    KIND_USERS,
)
from invoice_sorting.quota.plans import is_unlimited, limit_of, resolve_limits
from invoice_sorting.quota.snapshots import SnapshotThrottle, upsert_snapshot
from invoice_sorting.quota.state import QuotaReport, exceeded_message, readonly_notice, report_for
from invoice_sorting.quota.storage import StorageCache
from invoice_sorting.quota.usage import (
    QuotaUsage,
    count_active_members,
    count_expenses_created,
    megabytes,
)
from invoice_sorting.tenancy.runtime import TenantContext

logger = logging.getLogger(__name__)


def comparable(kind: str, raw: int) -> int:
    """把原始用量换算成与套餐上限同单位的数值（存储按 MB，其余按个数）。"""
    return megabytes(raw) if kind == KIND_STORAGE else raw


class QuotaService:
    """按请求计算用量与拦截原因；磁盘统计走缓存，快照写入走节流。"""

    def __init__(
        self,
        settings: Settings,
        storage: StorageCache | None = None,
        throttle: SnapshotThrottle | None = None,
        clock: Callable[[], datetime] = now,
    ) -> None:
        self._settings = settings
        self._storage = storage or StorageCache()
        self._throttle = throttle or SnapshotThrottle()
        self._clock = clock

    @property
    def is_enforced(self) -> bool:
        """只有多账套部署才有套餐与额度。"""
        return self._settings.is_saas

    @property
    def today(self) -> date:
        """当前日期（Asia/Shanghai）：到期日与日快照都按它取。"""
        return self._clock().date()

    def forget_snapshots(self) -> None:
        self._throttle.forget()

    def report(self, control: Session, tenant: Tenant, context: TenantContext) -> QuotaReport:
        """额度页面用的完整结果；顺带更新当天的用量快照。"""
        if not self.is_enforced:
            return QuotaReport(is_enforced=False)
        usage = self._usage(control, tenant, context)
        self._record(control, tenant, context.slug, self._snapshot_values(usage))
        return report_for(
            resolve_limits(control, tenant), usage, tenant.status, tenant.expires_on, self.today
        )

    def block(
        self, control: Session, tenant: Tenant, context: TenantContext, kinds: tuple[str, ...]
    ) -> WriteBlock | None:
        """写请求是否应被拒绝：先看租户状态，再逐项看额度（先命中先返回）。"""
        if not self.is_enforced:
            return None
        notice = readonly_notice(tenant.status, tenant.expires_on, self.today)
        if notice.is_readonly:
            return WriteBlock(code=BLOCK_CODE_READONLY, message=notice.message)
        limits = resolve_limits(control, tenant)
        for kind in kinds:
            limit = limit_of(limits, kind)
            if is_unlimited(limit):
                continue
            raw = self._measure(kind, control, tenant, context)
            used = comparable(kind, raw)
            if used >= limit:
                return WriteBlock(
                    code=BLOCK_CODE_QUOTA, message=exceeded_message(limits, kind, used)
                )
        return None

    def _usage(self, control: Session, tenant: Tenant, context: TenantContext) -> QuotaUsage:
        reading = self._storage.get(context.slug, context.settings.library_dir)
        return QuotaUsage(
            users=self._measure(KIND_USERS, control, tenant, context),
            storage_bytes=reading.bytes_used,
            expenses_this_month=self._measure(KIND_EXPENSES, control, tenant, context),
            storage_measured_at=reading.measured_at,
            storage_is_stale=reading.is_stale,
        )

    def _measure(self, kind: str, control: Session, tenant: Tenant, context: TenantContext) -> int:
        """单项原始用量（存储为字节，其余为个数）。"""
        if kind == KIND_USERS:
            return count_active_members(control, tenant.id)
        if kind == KIND_STORAGE:
            return self._storage.get(context.slug, context.settings.library_dir).bytes_used
        if kind == KIND_EXPENSES:
            with context.session_factory() as business:
                return count_expenses_created(business, self._clock())
        return 0

    @staticmethod
    def _snapshot_values(usage: QuotaUsage) -> dict[str, int]:
        return {
            KIND_USERS: usage.users,
            KIND_STORAGE: usage.storage_bytes,
            KIND_EXPENSES: usage.expenses_this_month,
        }

    def _record(self, control: Session, tenant: Tenant, slug: str, values: dict[str, int]) -> None:
        """写当天快照；失败只记日志，不影响本次请求。"""
        day = self.today
        if not values or not self._throttle.should_write(slug, day):
            return
        try:
            upsert_snapshot(control, tenant.id, day, values)
        except Exception:  # noqa: BLE001 - 快照是运营数据，不能让它挡住业务请求
            logger.exception("写入账套 %s 的用量快照失败", slug)
            control.rollback()
