"""套餐管理 API（仅平台管理员）：增删改查；被账套引用的套餐不能删除。"""

from typing import Any

from fastapi import APIRouter

from invoice_sorting.common.errors import ok
from invoice_sorting.control.deps import ControlSessionDep
from invoice_sorting.control.platform_deps import PLATFORM_ADMIN_ONLY
from invoice_sorting.platform_admin.plans import (
    create_plan,
    delete_plan,
    list_plans,
    require_plan,
    update_plan,
)
from invoice_sorting.platform_admin.schemas import PlanCreate, PlanUpdate
from invoice_sorting.platform_admin.serializers import serialize_plan

router = APIRouter(
    prefix="/api/platform/plans", tags=["平台套餐"], dependencies=PLATFORM_ADMIN_ONLY
)


@router.get("")
def read_plans(control: ControlSessionDep) -> dict[str, Any]:
    return ok([serialize_plan(plan) for plan in list_plans(control)])


@router.post("")
def post_plan(body: PlanCreate, control: ControlSessionDep) -> dict[str, Any]:
    return ok(serialize_plan(create_plan(control, body)))


@router.patch("/{plan_id}")
def patch_plan(plan_id: int, body: PlanUpdate, control: ControlSessionDep) -> dict[str, Any]:
    return ok(serialize_plan(update_plan(control, require_plan(control, plan_id), body)))


@router.delete("/{plan_id}")
def remove_plan(plan_id: int, control: ControlSessionDep) -> dict[str, Any]:
    delete_plan(control, require_plan(control, plan_id))
    return ok(None)
