"""平台后台的路径判断与账套解析（设计 5）。

平台运营后台通常通过**裸域名**访问（没有账套子域名），而认证中间件要求每个
`/api/*` 请求都能解析到账套。这里给平台路径单独定位账套：按登录会话所属账号的
成员关系来选，使 `/api/platform/*` 不会因为「解析不到账套」而 400/404，
未登录时也能得到清楚的 401，而不是含糊的「无法确定当前账套」。

安全前提：
- 只会选中该账号**确实有启用成员关系**的账套，拿不到就明确报错，不回退默认库；
- 平台接口另外一律要求平台管理员（control/platform_deps.py 的 PLATFORM_ADMIN_ONLY），
  且每个接口都用请求里显式的 slug 定位目标账套，不会拿这里解析出的账套读写业务数据。
"""

from typing import Any

from sqlalchemy.orm import Session

from invoice_sorting.common.errors import AppError

PLATFORM_PREFIX = "/api/platform"
MSG_LOGIN_REQUIRED = "请先登录"
MSG_NO_TENANT = "当前账号尚未加入任何账套，请联系管理员开通"


def is_platform_path(path: str) -> bool:
    return path == PLATFORM_PREFIX or path.startswith(f"{PLATFORM_PREFIX}/")


def platform_tenant_slug(app: Any, conn: Any) -> str | None:
    """平台路径专用的账套解析；非平台路径、单账套部署或关闭认证时返回 None。"""
    settings = app.state.settings
    if not settings.is_saas or not settings.auth_enabled:
        return None
    if not is_platform_path(conn.scope.get("path", "")):
        return None
    return _slug_from_session(app, conn)


def _slug_from_session(app: Any, conn: Any) -> str:
    from invoice_sorting.auth.http import read_session_token
    from invoice_sorting.auth.sessions import find_session

    token = read_session_token(conn)
    with app.state.control_session_factory() as control:
        row = find_session(control, token) if token else None
        if row is None:
            raise AppError(MSG_LOGIN_REQUIRED, status_code=401)
        return _pick_slug(control, row.account_id, row.tenant_id)


def _pick_slug(control: Session, account_id: int, current_id: int | None) -> str:
    """优先会话当前账套，其次该账号任意一个可进入的账套。"""
    from invoice_sorting.auth.service import account_tenants

    tenants = account_tenants(control, account_id)
    if not tenants:
        raise AppError(MSG_NO_TENANT, status_code=403)
    current = next((tenant for tenant in tenants if tenant.id == current_id), None)
    return (current or tenants[0]).slug
