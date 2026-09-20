"""套餐管理：额度为 0 表示不限制。被账套引用的套餐不允许删除。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from invoice_sorting.common.errors import AppError, ConflictError, NotFoundError
from invoice_sorting.control.models import Plan, Tenant
from invoice_sorting.platform_admin.schemas import PlanCreate, PlanUpdate

WHAT_PLAN = "套餐"
MSG_CODE_TAKEN = "套餐代码已存在"
MSG_PLAN_IN_USE = "该套餐已被 {count} 个账套使用，请先改用其他套餐"


def normalize_code(code: str) -> str:
    return (code or "").strip().lower()


def find_plan(control: Session, code: str) -> Plan | None:
    normalized = normalize_code(code)
    if not normalized:
        return None
    return control.scalar(select(Plan).where(Plan.code == normalized))


def require_plan(control: Session, plan_id: int) -> Plan:
    plan = control.get(Plan, plan_id)
    if plan is None:
        raise NotFoundError(WHAT_PLAN)
    return plan


def require_plan_by_code(control: Session, code: str) -> Plan:
    plan = find_plan(control, code)
    if plan is None:
        raise NotFoundError(WHAT_PLAN)
    return plan


def list_plans(control: Session) -> list[Plan]:
    return list(control.scalars(select(Plan).order_by(Plan.id)))


def create_plan(control: Session, body: PlanCreate) -> Plan:
    code = normalize_code(body.code)
    if find_plan(control, code) is not None:
        raise ConflictError(MSG_CODE_TAKEN)
    plan = Plan(
        code=code,
        name=body.name or code,
        max_users=body.max_users,
        max_storage_mb=body.max_storage_mb,
        max_expenses_per_month=body.max_expenses_per_month,
        features=dict(body.features),
    )
    control.add(plan)
    control.flush()
    return plan


def update_plan(control: Session, plan: Plan, body: PlanUpdate) -> Plan:
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(plan, field, dict(value) if field == "features" else value)
    control.flush()
    return plan


def tenant_count(control: Session, plan_id: int) -> int:
    return int(control.scalar(select(func.count(Tenant.id)).where(Tenant.plan_id == plan_id)) or 0)


def delete_plan(control: Session, plan: Plan) -> None:
    used = tenant_count(control, plan.id)
    if used:
        raise AppError(MSG_PLAN_IN_USE.format(count=used), status_code=409)
    control.delete(plan)
    control.flush()
