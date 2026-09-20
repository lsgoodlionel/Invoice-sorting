"""用户管理 API（仅管理员）：操作控制面账号 + 本账套成员关系，并同步业务库镜像。"""

from typing import Any

from fastapi import APIRouter

from invoice_sorting.auth.deps import ADMIN_ONLY, AdminDep
from invoice_sorting.common.errors import ok
from invoice_sorting.control.deps import ControlSessionDep, TenantRowDep
from invoice_sorting.control.members import list_members
from invoice_sorting.settings.deps import SessionDep
from invoice_sorting.users.schemas import PasswordReset, UserCreate, UserUpdate
from invoice_sorting.users.serializers import serialize_member
from invoice_sorting.users.service import (
    create_member,
    get_member_or_404,
    reset_member_password,
    update_member,
)
from invoice_sorting.users.sync import sync_member_into_session

router = APIRouter(prefix="/api/users", tags=["用户管理"], dependencies=ADMIN_ONLY)


@router.get("")
def read_users(control: ControlSessionDep, tenant: TenantRowDep) -> dict[str, Any]:
    return ok([serialize_member(member) for member in list_members(control, tenant.id)])


@router.post("")
def add_user(
    body: UserCreate, control: ControlSessionDep, tenant: TenantRowDep, session: SessionDep
) -> dict[str, Any]:
    member = create_member(control, tenant.id, body)
    payload = serialize_member(member)
    sync_member_into_session(session, member)
    return ok(payload)


@router.patch("/{user_id}")
def patch_user(
    user_id: int,
    body: UserUpdate,
    control: ControlSessionDep,
    tenant: TenantRowDep,
    session: SessionDep,
    actor: AdminDep,
) -> dict[str, Any]:
    member = update_member(control, actor, get_member_or_404(control, tenant.id, user_id), body)
    payload = serialize_member(member)
    sync_member_into_session(session, member)
    return ok(payload)


@router.post("/{user_id}/password")
def reset_password(
    user_id: int, body: PasswordReset, control: ControlSessionDep, tenant: TenantRowDep
) -> dict[str, Any]:
    reset_member_password(control, get_member_or_404(control, tenant.id, user_id), body.password)
    return ok(None)
