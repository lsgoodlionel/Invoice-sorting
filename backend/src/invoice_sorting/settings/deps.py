"""路由共用依赖：数据库会话与应用配置（均指向当前请求所属租户）。"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from invoice_sorting.config import Settings
from invoice_sorting.tenancy.deps import get_config, get_session, get_tenant
from invoice_sorting.tenancy.runtime import TenantContext


def get_engine(tenant: Annotated[TenantContext, Depends(get_tenant)]) -> Engine:
    return tenant.engine


SessionDep = Annotated[Session, Depends(get_session)]
ConfigDep = Annotated[Settings, Depends(get_config)]
EngineDep = Annotated[Engine, Depends(get_engine)]
