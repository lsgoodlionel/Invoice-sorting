"""认证 API：状态、设置 admin 初始密码、登录、退出、修改本人密码。

登录全部走控制面账号；成功后把控制面身份同步进当前账套的用户镜像。
"""

from typing import Any

from fastapi import APIRouter, Request, Response
from sqlalchemy.orm import Session

from invoice_sorting.auth.deps import CurrentUserDep
from invoice_sorting.auth.http import (
    USER_AGENT_HEADER,
    clear_session_cookie,
    client_ip,
    is_secure_request,
    read_session_token,
    set_session_cookie,
)
from invoice_sorting.auth.ratelimit import LoginRateLimiter, minutes_label
from invoice_sorting.auth.schemas import ChangePasswordBody, LoginBody, SetupBody
from invoice_sorting.auth.service import (
    MSG_WRONG_CREDENTIALS,
    Grant,
    change_password,
    is_password_set,
    login_with_password,
    setup_initial_password,
)
from invoice_sorting.auth.sessions import delete_session, session_tenant_id, validate_session
from invoice_sorting.auth.tenants import AuthTenantDep
from invoice_sorting.common.errors import AppError, ok
from invoice_sorting.control.deps import ControlSessionDep
from invoice_sorting.control.models import Tenant
from invoice_sorting.control.repository import get_tenant
from invoice_sorting.platform_admin.bootstrap import needs_platform_setup, setup_platform_admin
from invoice_sorting.tenancy.resolve import MSG_TENANT_REQUIRED
from invoice_sorting.users.sync import sync_member_into_tenant

router = APIRouter(prefix="/api/auth", tags=["登录认证"])

MSG_AUTH_DISABLED = "未启用登录认证，无法修改密码"


def _user_agent(request: Request) -> str:
    return request.headers.get(USER_AGENT_HEADER, "")


def tenant_brief(tenant: Tenant | None) -> dict[str, Any] | None:
    return {"slug": tenant.slug, "name": tenant.name} if tenant is not None else None


def tenancy_fields(request: Request, tenant: Tenant | None) -> dict[str, Any]:
    """账套相关字段只在多租户部署返回，单租户模式前端完全看不到账套概念。"""
    if not request.app.state.settings.is_saas:
        return {}
    return {"multi_tenant": True, "tenant": tenant_brief(tenant)}


def grant_response(
    request: Request, response: Response, control: Session, grant: Grant
) -> dict[str, Any]:
    """登录成功的统一出口：下发 Cookie 并把身份同步进该账套的用户镜像。"""
    control.commit()
    set_session_cookie(response, grant.token, is_secure_request(request))
    sync_member_into_tenant(request.app, grant.tenant.slug, grant.member)
    is_saas = request.app.state.settings.is_saas
    tenancy = {"tenant": tenant_brief(grant.tenant)} if is_saas else {}
    return ok({"authenticated": True, "user": grant.user.as_dict(), **tenancy})


def require_tenant(tenant: Tenant | None) -> Tenant:
    if tenant is None:
        raise AppError(MSG_TENANT_REQUIRED, status_code=400)
    return tenant


def _current_tenant(control: Session, tenant: Tenant | None, token: str | None) -> Tenant | None:
    """子域名没指定账套时，按会话记录的当前账套。"""
    if tenant is not None:
        return tenant
    tenant_id = session_tenant_id(control, token)
    return get_tenant(control, tenant_id) if tenant_id is not None else None


def _password_set(request: Request, control: Session, current: Tenant | None) -> bool:
    """是否已完成首次设置。

    定位到账套就看该账套的内置管理员；没定位到账套（SaaS 统一域名）时，
    空控制库表示还没有首个平台管理员，其余情况直接显示登录表单。
    """
    if current is not None:
        return is_password_set(control, current.id)
    return not needs_platform_setup(control, request.app.state.settings.is_saas)


@router.get("/status")
def auth_status(
    request: Request, response: Response, control: ControlSessionDep, tenant: AuthTenantDep
) -> dict[str, Any]:
    settings = request.app.state.settings
    token = read_session_token(request)
    current = _current_tenant(control, tenant, token)
    password_set = _password_set(request, control, current)
    authenticated, user = True, None
    if settings.auth_enabled:
        check = validate_session(control, token, current.id) if current is not None else None
        authenticated = bool(password_set and check is not None and check.is_valid)
        user = check.user.as_dict() if authenticated and check and check.user else None
        if check is not None and check.is_renewed and token:
            set_session_cookie(response, token, is_secure_request(request))
    return ok(
        {
            "auth_enabled": settings.auth_enabled,
            "password_set": password_set,
            "authenticated": authenticated,
            "user": user,
            **tenancy_fields(request, current if authenticated else None),
        }
    )


@router.post("/setup")
def auth_setup(
    body: SetupBody,
    request: Request,
    response: Response,
    control: ControlSessionDep,
    tenant: AuthTenantDep,
) -> dict[str, Any]:
    """首次设置：单账套为内置管理员 admin 设密码，多账套创建首个平台管理员。"""
    agent = _user_agent(request)
    if request.app.state.settings.is_saas:
        grant = setup_platform_admin(control, body.username, body.password, agent)
    else:
        grant = setup_initial_password(control, require_tenant(tenant), body.password, agent)
    return grant_response(request, response, control, grant)


@router.post("/login")
def auth_login(
    body: LoginBody,
    request: Request,
    response: Response,
    control: ControlSessionDep,
    tenant: AuthTenantDep,
) -> dict[str, Any]:
    limiter: LoginRateLimiter = request.app.state.login_limiter
    key = client_ip(request)
    wait = limiter.retry_after(key)
    if wait:
        raise AppError(f"尝试次数过多，请 {minutes_label(wait)} 分钟后再试", status_code=429)
    grant = login_with_password(control, tenant, body.username, body.password, _user_agent(request))
    if grant is None:
        limiter.record_failure(key)
        raise AppError(MSG_WRONG_CREDENTIALS, status_code=401)
    limiter.reset(key)
    return grant_response(request, response, control, grant)


@router.post("/logout")
def auth_logout(request: Request, response: Response, control: ControlSessionDep) -> dict[str, Any]:
    delete_session(control, read_session_token(request))
    clear_session_cookie(response, is_secure_request(request))
    return ok(None)


@router.post("/password")
def auth_change_password(
    body: ChangePasswordBody,
    request: Request,
    control: ControlSessionDep,
    user: CurrentUserDep,
) -> dict[str, Any]:
    if user is None:
        raise AppError(MSG_AUTH_DISABLED, status_code=400)
    token = read_session_token(request)
    change_password(control, user.id, body.current_password, body.new_password, token)
    return ok(None)
