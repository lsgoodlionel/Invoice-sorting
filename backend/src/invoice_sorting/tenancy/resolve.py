"""租户解析（设计 3.2）。

优先级：子域名（配置了 tenant_host_suffix 时）→ 请求状态中的租户（批次二由认证写入）。
单租户模式固定 default，不解析子域名。SaaS 模式下解析不到租户必须报错——
任何情况下都不允许回退到默认库，否则会造成跨租户数据泄漏。
"""

from typing import Any

from invoice_sorting.common.errors import AppError
from invoice_sorting.config import DEFAULT_TENANT_SLUG, Settings
from invoice_sorting.control.repository import is_valid_slug

STATE_TENANT_KEY = "tenant_slug"
MSG_TENANT_REQUIRED = "无法确定当前账套，请重新登录"
MSG_TENANT_UNKNOWN = "账套不存在"


def slug_from_host(host: str, suffix: str) -> str | None:
    """从 `t1.example.com` 取 `t1`；未配置后缀、裸域名或多级子域名返回 None。"""
    if not suffix:
        return None
    name = (host or "").split(":")[0].strip().lower().rstrip(".")
    tail = suffix.strip().lower().lstrip(".").rstrip(".")
    if not name or not tail or not name.endswith(f".{tail}"):
        return None
    head = name[: -(len(tail) + 1)]
    return head if head and "." not in head else None


def slug_from_state(conn: Any) -> str | None:
    """批次二的认证中间件会把会话中的租户写入 scope state，本批只读取。"""
    state = getattr(conn, "scope", {}).get("state") or {}
    value = state.get(STATE_TENANT_KEY)
    return value.strip().lower() if isinstance(value, str) and value.strip() else None


def resolve_tenant_slug(settings: Settings, conn: Any) -> str:
    """定位当前请求所属租户的 slug；SaaS 模式下定位不到时抛出 400。"""
    if not settings.is_saas:
        return DEFAULT_TENANT_SLUG
    host = conn.headers.get("host", "") if getattr(conn, "headers", None) else ""
    slug = slug_from_host(host, settings.tenant_host_suffix) or slug_from_state(conn)
    # 形态不合法的 slug 视为未解析（不得据此拼出数据目录）
    if slug and is_valid_slug(slug):
        return slug
    raise AppError(MSG_TENANT_REQUIRED, status_code=400)
