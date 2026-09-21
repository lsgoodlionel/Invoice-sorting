"""搬迁接口共用的账套查询：显示名称与平台侧的 slug 校验。"""

from typing import Any

from invoice_sorting.common.errors import NotFoundError
from invoice_sorting.config import DEFAULT_TENANT_SLUG
from invoice_sorting.control.repository import find_tenant, require_slug

WHAT_TENANT = "账套"


def tenant_name(app: Any, slug: str) -> str:
    """账套显示名称（覆盖导入二次确认时要求输入的就是它）；找不到时退回 slug。"""
    with app.state.control_session_factory() as control:
        tenant = find_tenant(control, slug)
        return tenant.name if tenant is not None else slug


def require_known_tenant(app: Any, slug: str) -> str:
    """校验 slug 形态并确认账套已开通，避免平台侧误建一个空账套。"""
    normalized = require_slug(slug)
    if not app.state.settings.is_saas and normalized != DEFAULT_TENANT_SLUG:
        raise NotFoundError(WHAT_TENANT)
    with app.state.control_session_factory() as control:
        if find_tenant(control, normalized) is None:
            raise NotFoundError(WHAT_TENANT)
    return normalized
