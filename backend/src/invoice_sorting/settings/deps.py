"""路由共用依赖：数据库会话与应用配置。"""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from invoice_sorting.config import Settings
from invoice_sorting.db.session import get_session


def get_config(request: Request) -> Settings:
    return request.app.state.settings


SessionDep = Annotated[Session, Depends(get_session)]
ConfigDep = Annotated[Settings, Depends(get_config)]
