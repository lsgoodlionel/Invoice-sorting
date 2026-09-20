"""多租户测试辅助：在控制库中开通租户、按子域名发请求。"""

from typing import Any

from invoice_sorting.control.repository import create_tenant, find_tenant


def open_tenants(app: Any, *slugs: str) -> None:
    """在控制库中开通若干租户（业务库仍按需懒加载）。"""
    with app.state.control_session_factory() as control:
        for slug in slugs:
            create_tenant(control, slug, f"{slug} 账套")
        control.commit()


def host_headers(slug: str, suffix: str = "example.com") -> dict[str, str]:
    return {"Host": f"{slug}.{suffix}"}


def add_member(
    app: Any,
    slug: str,
    username: str,
    *,
    password: str = "member-pass-123",
    role: str = "member",
    display_name: str | None = None,
) -> int:
    """在控制库为某账套开通一个账号（业务库镜像由首次进入时补齐）。"""
    from invoice_sorting.auth.passwords import hash_password
    from invoice_sorting.control.repository import create_account, ensure_membership, find_account

    with app.state.control_session_factory() as control:
        tenant = find_tenant(control, slug)
        assert tenant is not None, slug
        account = find_account(control, username) or create_account(
            control, username, display_name or username, hash_password(password)
        )
        ensure_membership(control, account.id, tenant.id, role=role)
        control.commit()
        return account.id


def login_at(client, username: str, password: str = "member-pass-123", slug: str | None = None):
    """登录；给了 slug 就走该账套的子域名。"""
    headers = host_headers(slug) if slug else None
    body = {"username": username, "password": password}
    return client.post("/api/auth/login", json=body, headers=headers)
