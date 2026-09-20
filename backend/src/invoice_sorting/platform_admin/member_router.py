"""任意账套的成员管理 API（仅平台管理员）：成员列表、添加、停用/改角色、重置密码、邀请码。

目标账套由路径里的 slug 显式指定，与当前请求解析到的账套无关；
业务规则（不能停用自己、账套至少保留一名管理员）与租户内的用户管理完全一致。
"""

from typing import Any

from fastapi import APIRouter, Request

from invoice_sorting.common.errors import ok
from invoice_sorting.control.deps import ControlSessionDep
from invoice_sorting.control.members import Member, list_members
from invoice_sorting.control.models import Tenant
from invoice_sorting.control.platform_deps import PLATFORM_ADMIN_ONLY, PlatformAdminDep
from invoice_sorting.invites.service import list_invites
from invoice_sorting.platform_admin.members import add_member, issue_invite, mirror_member
from invoice_sorting.platform_admin.schemas import (
    InviteCreate,
    MemberCreate,
    MemberPassword,
    MemberUpdate,
)
from invoice_sorting.platform_admin.serializers import serialize_invite
from invoice_sorting.platform_admin.tenants import require_tenant
from invoice_sorting.users.schemas import UserUpdate
from invoice_sorting.users.serializers import serialize_member
from invoice_sorting.users.service import get_member_or_404, reset_member_password, update_member

router = APIRouter(
    prefix="/api/platform/tenants/{slug}", tags=["平台成员"], dependencies=PLATFORM_ADMIN_ONLY
)


def _saved(control: ControlSessionDep, request: Request, tenant: Tenant, member: Member) -> Any:
    """先落库控制面，再同步业务库镜像（镜像失败不影响本次结果）。"""
    payload = serialize_member(member)
    slug = tenant.slug
    control.commit()
    mirror_member(request.app, slug, member)
    return payload


@router.get("/members")
def read_members(slug: str, control: ControlSessionDep) -> dict[str, Any]:
    tenant = require_tenant(control, slug)
    return ok([serialize_member(member) for member in list_members(control, tenant.id)])


@router.post("/members")
def post_member(
    slug: str, body: MemberCreate, request: Request, control: ControlSessionDep
) -> dict[str, Any]:
    """新账号需填初始密码；已存在的账号直接加入该账套。"""
    tenant = require_tenant(control, slug)
    member = add_member(control, tenant, body)
    return ok(_saved(control, request, tenant, member))


@router.patch("/members/{account_id}")
def patch_member(
    slug: str,
    account_id: int,
    body: MemberUpdate,
    request: Request,
    control: ControlSessionDep,
    actor: PlatformAdminDep,
) -> dict[str, Any]:
    """改姓名、改角色、停用或恢复；停用后该账号在本账套的会话立即失效。"""
    tenant = require_tenant(control, slug)
    member = get_member_or_404(control, tenant.id, account_id)
    patch = UserUpdate(**body.model_dump(exclude_unset=True))
    updated = update_member(control, actor, member, patch)
    return ok(_saved(control, request, tenant, updated))


@router.post("/members/{account_id}/password")
def post_member_password(
    slug: str, account_id: int, body: MemberPassword, control: ControlSessionDep
) -> dict[str, Any]:
    """重置成员密码：该账号的全部会话立即失效。"""
    tenant = require_tenant(control, slug)
    reset_member_password(control, get_member_or_404(control, tenant.id, account_id), body.password)
    return ok(None)


@router.get("/invites")
def read_invites(slug: str, control: ControlSessionDep) -> dict[str, Any]:
    tenant = require_tenant(control, slug)
    return ok([serialize_invite(invite) for invite in list_invites(control, tenant.id)])


@router.post("/invites")
def post_invite(slug: str, body: InviteCreate, control: ControlSessionDep) -> dict[str, Any]:
    tenant = require_tenant(control, slug)
    return ok(serialize_invite(issue_invite(control, tenant, body)))
