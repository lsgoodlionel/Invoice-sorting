"""认证与租户的衔接：会话所选租户、子域名指定的租户、切换账套。

跨租户越权是本批最高风险，所以这里的每个出口都要么给出**已校验成员关系**的租户，
要么明确失败；任何情况下都不回退到默认库。
"""

from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from invoice_sorting.auth.sessions import MSG_NOT_A_MEMBER, session_tenant_id, set_session_tenant
from invoice_sorting.common.errors import AppError
from invoice_sorting.config import DEFAULT_TENANT_SLUG, Settings
from invoice_sorting.control.deps import ControlSessionDep, require_tenant_row
from invoice_sorting.control.members import Member, active_member
from invoice_sorting.control.models import Tenant
from invoice_sorting.control.repository import get_tenant, is_valid_slug, require_slug
from invoice_sorting.tenancy.resolve import slug_from_host

MSG_SINGLE_TENANT = "当前为单账套部署，无需切换账套"
MSG_SESSION_GONE = "登录状态已失效，请重新登录"


def session_tenant_slug(app: Any, token: str | None) -> str | None:
    """会话当前所选租户的 slug；用于在解析租户前写入请求状态。"""
    with app.state.control_session_factory() as control:
        tenant_id = session_tenant_id(control, token)
        tenant = get_tenant(control, tenant_id) if tenant_id is not None else None
        slug = tenant.slug if tenant is not None else None
        control.commit()  # 顺带落盘对过期会话行的清理
    return slug if slug and is_valid_slug(slug) else None


def host_tenant_slug(settings: Settings, request: Request) -> str | None:
    """认证端点使用的租户提示：单租户固定 default；SaaS 只认子域名。"""
    if not settings.is_saas:
        return DEFAULT_TENANT_SLUG
    return slug_from_host(request.headers.get("host", ""), settings.tenant_host_suffix)


def get_auth_tenant(request: Request, control: ControlSessionDep) -> Tenant | None:
    """登录/设置密码等公开端点所处的账套；SaaS 统一域名下为 None（登录后按账号归属定位）。"""
    slug = host_tenant_slug(request.app.state.settings, request)
    return require_tenant_row(control, slug) if slug else None


def require_member(control: Session, account_id: int, tenant: Tenant) -> Member:
    """账号在该租户内必须有启用中的成员关系，否则 403。"""
    member = active_member(control, account_id, tenant.id)
    if member is None:
        raise AppError(MSG_NOT_A_MEMBER, status_code=403)
    return member


def switch_tenant(
    control: Session, token: str | None, account_id: int, slug: str
) -> tuple[Member, Tenant]:
    """切换会话所选租户：先校验成员关系，再改会话。"""
    tenant = require_tenant_row(control, require_slug(slug))
    member = require_member(control, account_id, tenant)
    if not set_session_tenant(control, token, tenant.id):
        raise AppError(MSG_SESSION_GONE, status_code=401)
    return member, tenant


AuthTenantDep = Annotated[Tenant | None, Depends(get_auth_tenant)]
