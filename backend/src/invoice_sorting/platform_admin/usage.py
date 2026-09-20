"""账套用量与成员数的批量查询：每类信息一条聚合 SQL，避免按账套逐个查询（N+1）。

用量取自批次三写入的 `usage_snapshot` 日快照，平台后台只读不写。
"""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from invoice_sorting.control.models import (
    TENANT_STATUS_ACTIVE,
    Account,
    Membership,
    Tenant,
    UsageSnapshot,
)


def member_counts(control: Session, tenant_ids: Sequence[int]) -> dict[int, int]:
    """每个账套启用中的成员数。"""
    if not tenant_ids:
        return {}
    rows = control.execute(
        select(Membership.tenant_id, func.count(Membership.id))
        .where(Membership.tenant_id.in_(tenant_ids), Membership.is_active.is_(True))
        .group_by(Membership.tenant_id)
    ).all()
    return {tenant_id: count for tenant_id, count in rows}


def latest_usage(control: Session, tenant_ids: Sequence[int]) -> dict[int, UsageSnapshot]:
    """每个账套最近一天的用量快照；没有快照的账套不出现在结果中。"""
    if not tenant_ids:
        return {}
    newest = (
        select(UsageSnapshot.tenant_id, func.max(UsageSnapshot.day).label("day"))
        .where(UsageSnapshot.tenant_id.in_(tenant_ids))
        .group_by(UsageSnapshot.tenant_id)
        .subquery()
    )
    rows = control.scalars(
        select(UsageSnapshot).join(
            newest,
            (UsageSnapshot.tenant_id == newest.c.tenant_id) & (UsageSnapshot.day == newest.c.day),
        )
    )
    return {row.tenant_id: row for row in rows}


def platform_totals(control: Session) -> dict[str, int]:
    """平台概览：账套数、活跃账套数、账号数与最近快照的用量合计。"""
    tenant_ids = list(control.scalars(select(Tenant.id)))
    snapshots = latest_usage(control, tenant_ids).values()
    return {
        "tenants": len(tenant_ids),
        "active_tenants": _count(
            control, select(func.count(Tenant.id)).where(Tenant.status == TENANT_STATUS_ACTIVE)
        ),
        "accounts": _count(control, select(func.count(Account.id))),
        "storage_bytes": sum(row.storage_bytes for row in snapshots),
        "expenses_created": sum(row.expenses_created for row in snapshots),
    }


def _count(control: Session, statement) -> int:  # noqa: ANN001 - SQLAlchemy 语句类型
    return int(control.scalar(statement) or 0)
