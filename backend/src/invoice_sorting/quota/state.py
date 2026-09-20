"""额度与租户状态的判定（纯函数，不碰数据库与磁盘）。

两件事：
1. 租户是否进入只读（停用/关闭/订阅到期），以及对应的中文原因；
2. 三项额度各自的上限、当前值、是否已达上限，以及超限时的提示文案。

“已达上限”即 `当前 >= 上限`：此时再做一次就会超出，所以直接拒绝。
"""

from dataclasses import dataclass, field
from datetime import date

from invoice_sorting.control.models import (
    TENANT_STATUS_ACTIVE,
    TENANT_STATUS_CLOSED,
    TENANT_STATUS_SUSPENDED,
)
from invoice_sorting.quota.constants import (
    KINDS,
    LABELS,
    MSG_CLOSED,
    MSG_EXCEEDED,
    MSG_EXPIRED,
    MSG_SUSPENDED,
    REASON_CLOSED,
    REASON_EXPIRED,
    REASON_SUSPENDED,
    UNITS,
)
from invoice_sorting.quota.plans import PlanLimits, is_unlimited, limit_of
from invoice_sorting.quota.usage import QuotaUsage

STATUS_NOTICES = {
    TENANT_STATUS_SUSPENDED: (REASON_SUSPENDED, MSG_SUSPENDED),
    TENANT_STATUS_CLOSED: (REASON_CLOSED, MSG_CLOSED),
}


@dataclass(frozen=True)
class ReadonlyNotice:
    """只读原因；reason 为空表示可写。"""

    reason: str = ""
    message: str = ""

    @property
    def is_readonly(self) -> bool:
        return bool(self.reason)


@dataclass(frozen=True)
class LimitLine:
    """一项额度的当前情况，直接对应界面上的一行。"""

    key: str
    label: str
    unit: str
    limit: int
    used: int
    remaining: int | None
    is_unlimited: bool
    is_exceeded: bool


@dataclass(frozen=True)
class QuotaReport:
    """GET /api/quota 的完整结果；单账套部署下 is_enforced 为 False，其余字段留空。"""

    is_enforced: bool
    status: str = TENANT_STATUS_ACTIVE
    expires_on: date | None = None
    notice: ReadonlyNotice = ReadonlyNotice()
    plan: PlanLimits | None = None
    usage: QuotaUsage | None = None
    lines: tuple[LimitLine, ...] = field(default_factory=tuple)

    @property
    def is_readonly(self) -> bool:
        return self.notice.is_readonly


def readonly_notice(status: str, expires_on: date | None, today: date) -> ReadonlyNotice:
    """租户状态优先于到期日：停用的账套即使还没到期也不可写。到期日当天仍可写。"""
    if status != TENANT_STATUS_ACTIVE:
        reason, message = STATUS_NOTICES.get(status, (REASON_SUSPENDED, MSG_SUSPENDED))
        return ReadonlyNotice(reason=reason, message=message)
    if expires_on is not None and expires_on < today:
        return ReadonlyNotice(
            reason=REASON_EXPIRED, message=MSG_EXPIRED.format(day=expires_on.isoformat())
        )
    return ReadonlyNotice()


def limit_line(limits: PlanLimits, kind: str, used: int) -> LimitLine:
    limit = limit_of(limits, kind)
    unlimited = is_unlimited(limit)
    return LimitLine(
        key=kind,
        label=LABELS.get(kind, kind),
        unit=UNITS.get(kind, ""),
        limit=limit,
        used=used,
        remaining=None if unlimited else max(0, limit - used),
        is_unlimited=unlimited,
        is_exceeded=not unlimited and used >= limit,
    )


def build_lines(
    limits: PlanLimits, users: int, storage_mb: int, expenses: int
) -> tuple[LimitLine, ...]:
    """三项额度按固定顺序返回，界面可直接逐行渲染。"""
    used_by_kind = dict(zip(KINDS, (users, storage_mb, expenses), strict=True))
    return tuple(limit_line(limits, kind, used_by_kind[kind]) for kind in KINDS)


def exceeded_message(limits: PlanLimits, kind: str, used: int) -> str:
    """超限文案：指明哪一项、上限多少、当前多少、可以怎么办。"""
    template = MSG_EXCEEDED[kind]
    return template.format(plan=limits.name, limit=limit_of(limits, kind), used=used)


def report_for(
    limits: PlanLimits, usage: QuotaUsage, status: str, expires_on: date | None, today: date
) -> QuotaReport:
    return QuotaReport(
        is_enforced=True,
        status=status,
        expires_on=expires_on,
        notice=readonly_notice(status, expires_on, today),
        plan=limits,
        usage=usage,
        lines=build_lines(limits, usage.users, usage.storage_mb, usage.expenses_this_month),
    )
