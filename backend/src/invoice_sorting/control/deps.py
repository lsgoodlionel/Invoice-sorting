"""控制库依赖：每个请求一个控制库会话，以及“当前请求所属租户”在控制库中的行。

与业务库会话（settings/deps.py）相互独立：认证、成员与邀请码只读写控制库，
业务数据仍在租户库；两者都解析不到时直接报错，不会回退到默认库。
"""

from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from invoice_sorting.common.errors import AppError
from invoice_sorting.control.models import Tenant
from invoice_sorting.control.repository import find_tenant
from invoice_sorting.tenancy.resolve import MSG_TENANT_UNKNOWN


def control_session_factory(app: Any) -> sessionmaker[Session]:
    return app.state.control_session_factory


def get_control_session(request: Request) -> Iterator[Session]:
    session = control_session_factory(request.app)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def require_tenant_row(control: Session, slug: str) -> Tenant:
    """按 slug 取控制库中的租户行；不存在时 404（单租户模式启动时已确保存在）。"""
    tenant = find_tenant(control, slug)
    if tenant is None:
        raise AppError(MSG_TENANT_UNKNOWN, status_code=404)
    return tenant


def get_tenant_row(request: Request, control: Annotated[Session, Depends(get_control_session)]):
    """当前请求所属租户在控制库中的行（先按 tenancy 规则解析 slug）。"""
    from invoice_sorting.tenancy.deps import get_tenant

    return require_tenant_row(control, get_tenant(request).slug)


ControlSessionDep = Annotated[Session, Depends(get_control_session)]
TenantRowDep = Annotated[Tenant, Depends(get_tenant_row)]
