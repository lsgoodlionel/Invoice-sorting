"""平台管理员依赖：`/api/platform/*` 只允许控制面标记为平台管理员的账号访问。

租户管理员只能管理自己的账套，跨账套操作（导出别人的数据、开通与停用账套）必须是平台管理员。
单租户部署（deployment_mode=single）没有平台概念，管理员即平台管理员。
"""

from typing import Annotated, Any

from fastapi import Depends, Request

from invoice_sorting.auth.context import AuthUser
from invoice_sorting.auth.deps import get_current_user, require_admin
from invoice_sorting.common.errors import AppError
from invoice_sorting.control.deps import control_session_factory
from invoice_sorting.control.repository import get_account

MSG_PLATFORM_ADMIN_REQUIRED = "需要平台管理员权限"


def is_platform_admin(app: Any, user: AuthUser | None) -> bool:
    if user is None:
        return False
    with control_session_factory(app)() as control:
        account = get_account(control, user.id)
        return bool(account is not None and account.is_active and account.is_platform_admin)


def require_platform_admin(request: Request) -> AuthUser | None:
    """非平台管理员 403；单租户部署退化为管理员校验；关闭认证时放行。"""
    settings = request.app.state.settings
    if not settings.auth_enabled:
        return get_current_user(request)
    user = require_admin(request)
    if not settings.is_saas:
        return user
    if not is_platform_admin(request.app, user):
        raise AppError(MSG_PLATFORM_ADMIN_REQUIRED, status_code=403)
    return user


PlatformAdminDep = Annotated[AuthUser | None, Depends(require_platform_admin)]
PLATFORM_ADMIN_ONLY = [Depends(require_platform_admin)]
