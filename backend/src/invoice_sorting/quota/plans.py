"""套餐额度的取值：来自控制库 `plan`，未绑定套餐时回落到内置免费套餐。

任何一项为 0（或负数）表示**该项不限制**，与 control/models.py 中 Plan 的既有约定一致。
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.control.models import Plan, Tenant
from invoice_sorting.quota.constants import KIND_EXPENSES, KIND_STORAGE, KIND_USERS

logger = logging.getLogger(__name__)

LIMIT_FIELDS = {
    KIND_USERS: "max_users",
    KIND_STORAGE: "max_storage_mb",
    KIND_EXPENSES: "max_expenses_per_month",
}


@dataclass(frozen=True)
class PlanLimits:
    """某租户当前适用的额度；与数据库行解耦，便于在请求外传递与比较。"""

    code: str
    name: str
    max_users: int = 0
    max_storage_mb: int = 0
    max_expenses_per_month: int = 0
    features: dict[str, Any] = field(default_factory=dict)


# 内置默认套餐：租户未绑定套餐（plan_id 为空）时按它计算，不需要数据库里有这一行。
# ensure_default_plan() 会把同样的数值写入控制库，供运营后台在界面上直接选用。
FREE_PLAN = PlanLimits(
    code="free",
    name="免费版",
    max_users=3,
    max_storage_mb=1024,
    max_expenses_per_month=200,
)


def is_unlimited(limit: int) -> bool:
    return limit <= 0


def limit_of(limits: PlanLimits, kind: str) -> int:
    """取某一项的上限；未知项按不限制处理。"""
    field_name = LIMIT_FIELDS.get(kind)
    return int(getattr(limits, field_name, 0) or 0) if field_name else 0


def plan_limits(plan: Plan) -> PlanLimits:
    return PlanLimits(
        code=plan.code,
        name=plan.name or plan.code,
        max_users=int(plan.max_users or 0),
        max_storage_mb=int(plan.max_storage_mb or 0),
        max_expenses_per_month=int(plan.max_expenses_per_month or 0),
        features=dict(plan.features or {}),
    )


def resolve_limits(control: Session, tenant: Tenant) -> PlanLimits:
    """租户当前适用的额度；套餐被删除或未绑定时都回落到免费套餐，不让请求失败。"""
    if tenant.plan_id is None:
        return FREE_PLAN
    plan = control.get(Plan, tenant.plan_id)
    if plan is None:
        logger.warning("账套 %s 绑定的套餐 %s 不存在，按免费套餐处理", tenant.slug, tenant.plan_id)
        return FREE_PLAN
    return plan_limits(plan)


def ensure_default_plan(control: Session) -> Plan:
    """在控制库中写入默认套餐（幂等）；已存在时不覆盖运营改过的数值。"""
    found = control.scalar(select(Plan).where(Plan.code == FREE_PLAN.code))
    if found is not None:
        return found
    plan = Plan(
        code=FREE_PLAN.code,
        name=FREE_PLAN.name,
        max_users=FREE_PLAN.max_users,
        max_storage_mb=FREE_PLAN.max_storage_mb,
        max_expenses_per_month=FREE_PLAN.max_expenses_per_month,
        features=dict(FREE_PLAN.features),
    )
    control.add(plan)
    control.flush()
    return plan
