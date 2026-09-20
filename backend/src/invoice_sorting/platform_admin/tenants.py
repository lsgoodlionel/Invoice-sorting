"""账套管理：列表（含套餐、成员数、用量）、开通、改名改套餐改到期日、停用恢复与关闭。"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from invoice_sorting.common.errors import AppError
from invoice_sorting.control.members import Member
from invoice_sorting.control.models import Invite, Plan, Tenant, UsageSnapshot
from invoice_sorting.control.repository import create_tenant, find_tenant, require_slug
from invoice_sorting.platform_admin.members import add_member, issue_invite
from invoice_sorting.platform_admin.plans import require_plan_by_code
from invoice_sorting.platform_admin.schemas import (
    InviteCreate,
    MemberCreate,
    TenantCreate,
    TenantStatus,
    TenantUpdate,
)
from invoice_sorting.platform_admin.usage import latest_usage, member_counts
from invoice_sorting.users.repository import UserRole

WHAT_TENANT = "账套"
MSG_TENANT_MISSING = "账套不存在"
MSG_ADMIN_REQUIRED = "请填写首个管理员的用户名与初始密码，或改为签发邀请码"
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class TenantView:
    """列表中的一行：账套本身 + 套餐 + 成员数 + 最近一天用量。"""

    tenant: Tenant
    plan: Plan | None = None
    member_count: int = 0
    usage: UsageSnapshot | None = None


@dataclass(frozen=True)
class TenantPage:
    items: list[TenantView]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True)
class OpenResult:
    """开通结果：可能带首个管理员，或一张管理员邀请码。"""

    tenant: Tenant
    member: Member | None = None
    invite: Invite | None = None


def require_tenant(control: Session, slug: str) -> Tenant:
    tenant = find_tenant(control, require_slug(slug))
    if tenant is None:
        raise AppError(MSG_TENANT_MISSING, status_code=404)
    return tenant


def _search_filter(query: Any, keyword: str) -> Any:
    like = f"%{keyword}%"
    return query.where(or_(Tenant.slug.like(like), Tenant.name.like(like)))


def list_tenants(
    control: Session, keyword: str = "", page: int = 1, page_size: int = DEFAULT_PAGE_SIZE
) -> TenantPage:
    """按创建时间倒序分页；成员数与用量各用一条聚合查询补齐。"""
    size = max(1, min(page_size, MAX_PAGE_SIZE))
    current = max(1, page)
    keyword = (keyword or "").strip()
    rows = select(Tenant).order_by(Tenant.id.desc())
    counter = select(func.count(Tenant.id))
    if keyword:
        rows, counter = _search_filter(rows, keyword), _search_filter(counter, keyword)
    total = int(control.scalar(counter) or 0)
    tenants = list(control.scalars(rows.offset((current - 1) * size).limit(size)))
    return TenantPage(items=_decorate(control, tenants), total=total, page=current, page_size=size)


def _decorate(control: Session, tenants: list[Tenant]) -> list[TenantView]:
    ids = [tenant.id for tenant in tenants]
    counts = member_counts(control, ids)
    usage = latest_usage(control, ids)
    plans = {plan.id: plan for plan in control.scalars(select(Plan))}
    return [
        TenantView(
            tenant=tenant,
            plan=plans.get(tenant.plan_id) if tenant.plan_id else None,
            member_count=counts.get(tenant.id, 0),
            usage=usage.get(tenant.id),
        )
        for tenant in tenants
    ]


def describe(control: Session, tenant: Tenant) -> TenantView:
    return _decorate(control, [tenant])[0]


def open_tenant(control: Session, body: TenantCreate) -> OpenResult:
    """开通账套，并按需开通首个管理员账号或签发管理员邀请码。"""
    if not body.admin_username and not body.with_invite:
        raise AppError(MSG_ADMIN_REQUIRED, status_code=400)
    plan = require_plan_by_code(control, body.plan_code) if body.plan_code else None
    tenant = create_tenant(control, body.slug, body.name or body.slug, plan.id if plan else None)
    tenant.expires_on = body.expires_on
    member = _open_first_admin(control, tenant, body)
    admin_invite = InviteCreate(role=UserRole.ADMIN)
    invite = issue_invite(control, tenant, admin_invite) if member is None else None
    control.flush()
    return OpenResult(tenant=tenant, member=member, invite=invite)


def _open_first_admin(control: Session, tenant: Tenant, body: TenantCreate) -> Member | None:
    if not body.admin_username:
        return None
    return add_member(
        control,
        tenant,
        MemberCreate(
            username=body.admin_username,
            display_name=body.admin_display_name,
            password=body.admin_password,
            role=UserRole.ADMIN,
        ),
    )


def update_tenant(control: Session, tenant: Tenant, body: TenantUpdate) -> Tenant:
    """只修改客户端明确传了的字段；传 null 表示清空（套餐、永久有效）。"""
    changed = body.model_fields_set
    if "name" in changed and body.name:
        tenant.name = body.name
    if "plan_code" in changed:
        plan = require_plan_by_code(control, body.plan_code) if body.plan_code else None
        tenant.plan_id = plan.id if plan is not None else None
    if "expires_on" in changed:
        tenant.expires_on = body.expires_on
    if "status" in changed and body.status is not None:
        tenant.status = str(body.status)
    control.flush()
    return tenant


def is_runnable(tenant: Tenant) -> bool:
    """账套是否仍可对外服务；停用与关闭都要释放其数据库连接。"""
    return tenant.status == str(TenantStatus.ACTIVE)
