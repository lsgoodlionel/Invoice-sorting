"""认证相关依赖：当前用户、管理员权限。"""

from typing import Annotated

from fastapi import Depends, Request

from invoice_sorting.auth.context import AuthUser
from invoice_sorting.common.errors import AppError
from invoice_sorting.users.repository import UserRole

MSG_ADMIN_REQUIRED = "需要管理员权限"
STATE_USER_KEY = "auth_user"


def get_current_user(request: Request) -> AuthUser | None:
    """认证中间件写入的当前用户；公开端点、关闭认证时为 None。"""
    return getattr(request.state, STATE_USER_KEY, None)


def require_admin(request: Request) -> AuthUser | None:
    """非管理员 403；关闭认证时放行。"""
    user = get_current_user(request)
    if not request.app.state.settings.auth_enabled:
        return user
    if user is None or user.role != UserRole.ADMIN:
        raise AppError(MSG_ADMIN_REQUIRED, status_code=403)
    return user


CurrentUserDep = Annotated[AuthUser | None, Depends(get_current_user)]
AdminDep = Annotated[AuthUser | None, Depends(require_admin)]
ADMIN_ONLY = [Depends(require_admin)]
