"""多租户测试辅助：在控制库中开通租户、按子域名发请求。"""

from typing import Any

from invoice_sorting.control.repository import create_tenant


def open_tenants(app: Any, *slugs: str) -> None:
    """在控制库中开通若干租户（业务库仍按需懒加载）。"""
    with app.state.control_session_factory() as control:
        for slug in slugs:
            create_tenant(control, slug, f"{slug} 账套")
        control.commit()


def host_headers(slug: str, suffix: str = "example.com") -> dict[str, str]:
    return {"Host": f"{slug}.{suffix}"}
