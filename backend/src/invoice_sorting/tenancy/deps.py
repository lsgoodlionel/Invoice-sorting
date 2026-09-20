"""租户依赖：把当前请求映射到所属租户的配置、引擎与数据库会话。

业务路由继续使用 SessionDep / ConfigDep，无需感知租户；
所有入口都经过这里，解析不到租户时直接报错，不会回退到别的库。
"""

from collections.abc import Iterator
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from invoice_sorting.common.errors import AppError
from invoice_sorting.config import Settings
from invoice_sorting.control.repository import find_tenant
from invoice_sorting.tenancy.resolve import MSG_TENANT_UNKNOWN, resolve_tenant_slug
from invoice_sorting.tenancy.runtime import TenantContext, TenantRuntime

STATE_CONTEXT_KEY = "tenant_context"


def tenant_for_connection(app: Any, conn: Any) -> TenantContext:
    """解析并加载当前连接所属租户；同一请求内复用已解析结果。"""
    state = conn.scope.setdefault("state", {})
    cached = state.get(STATE_CONTEXT_KEY)
    if isinstance(cached, TenantContext):
        return cached
    context = load_tenant(app, _resolve_slug(app, conn))
    state[STATE_CONTEXT_KEY] = context
    return context


def _resolve_slug(app: Any, conn: Any) -> str:
    """平台后台常从裸域名访问，先按登录账号定位账套；其余请求走常规解析规则。"""
    from invoice_sorting.platform_admin.scope import platform_tenant_slug

    return platform_tenant_slug(app, conn) or resolve_tenant_slug(app.state.settings, conn)


def load_tenant(app: Any, slug: str) -> TenantContext:
    """SaaS 模式先在控制库确认租户存在，再交给运行时加载（单租户模式启动时已确保）。"""
    settings: Settings = app.state.settings
    if settings.is_saas and not _is_known_tenant(app, slug):
        # 租户状态与额度的校验在批次三补充，本批只确认租户已开通
        raise AppError(MSG_TENANT_UNKNOWN, status_code=404)
    runtime: TenantRuntime = app.state.tenants
    return runtime.get(slug)


def _is_known_tenant(app: Any, slug: str) -> bool:
    with app.state.control_session_factory() as control:
        return find_tenant(control, slug) is not None


def get_tenant(request: Request) -> TenantContext:
    return tenant_for_connection(request.app, request)


def get_config(request: Request) -> Settings:
    return get_tenant(request).settings


def get_session(request: Request) -> Iterator[Session]:
    """FastAPI 依赖：每个请求一个当前租户的会话，异常时回滚。"""
    session = get_tenant(request).session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
