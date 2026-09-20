"""账套切换 API（仅多租户部署）：列出可进入的账套、切换当前账套。

单租户部署下两个端点都返回 404，前端因此完全看不到账套概念。
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, StrictStr

from invoice_sorting.auth.deps import CurrentUserDep
from invoice_sorting.auth.http import read_session_token
from invoice_sorting.auth.service import account_tenants
from invoice_sorting.auth.sessions import member_user, session_tenant_id
from invoice_sorting.auth.tenants import MSG_SINGLE_TENANT, switch_tenant
from invoice_sorting.common.errors import AppError, ok
from invoice_sorting.control.deps import ControlSessionDep
from invoice_sorting.control.models import Tenant
from invoice_sorting.control.repository import SLUG_PATTERN
from invoice_sorting.users.sync import sync_member_into_tenant

router = APIRouter(prefix="/api/auth", tags=["账套切换"])

MSG_LOGIN_REQUIRED = "请先登录"
SLUG_MAX = 50


class SwitchTenantBody(BaseModel):
    slug: Annotated[StrictStr, Field(max_length=SLUG_MAX, pattern=SLUG_PATTERN.pattern)]


def require_saas(request: Request) -> None:
    """单租户部署不暴露账套能力。"""
    if not request.app.state.settings.is_saas:
        raise AppError(MSG_SINGLE_TENANT, status_code=404)


def _serialize(tenant: Tenant, current_id: int | None) -> dict[str, Any]:
    return {
        "slug": tenant.slug,
        "name": tenant.name,
        "is_current": tenant.id == current_id,
    }


SAAS_ONLY = [Depends(require_saas)]


@router.get("/tenants", dependencies=SAAS_ONLY)
def read_tenants(
    request: Request, control: ControlSessionDep, user: CurrentUserDep
) -> dict[str, Any]:
    """当前账号可进入的账套（成员关系与账套均启用）。"""
    if user is None:
        raise AppError(MSG_LOGIN_REQUIRED, status_code=401)
    current_id = session_tenant_id(control, read_session_token(request))
    tenants = account_tenants(control, user.id)
    return ok([_serialize(tenant, current_id) for tenant in tenants])


@router.post("/switch-tenant", dependencies=SAAS_ONLY)
def post_switch_tenant(
    body: SwitchTenantBody, request: Request, control: ControlSessionDep, user: CurrentUserDep
) -> dict[str, Any]:
    """切换当前账套；没有有效成员关系时 403。"""
    if user is None:
        raise AppError(MSG_LOGIN_REQUIRED, status_code=401)
    token = read_session_token(request)
    member, tenant = switch_tenant(control, token, user.id, body.slug)
    payload = {"authenticated": True, "user": member_user(member).as_dict()}
    slug, name = tenant.slug, tenant.name
    control.commit()
    sync_member_into_tenant(request.app, slug, member)
    return ok({**payload, "tenant": {"slug": slug, "name": name}})
