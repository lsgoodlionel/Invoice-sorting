"""额度测试辅助：给账套指定套餐、改状态与到期日、读取额度快照。"""

from datetime import date
from typing import Any

from invoice_sorting.control.models import Plan
from invoice_sorting.control.repository import find_tenant

TEAM_PLAN_CODE = "team"


def set_plan(
    app: Any,
    slug: str,
    *,
    code: str = TEAM_PLAN_CODE,
    name: str = "团队版",
    max_users: int = 0,
    max_storage_mb: int = 0,
    max_expenses_per_month: int = 0,
    features: dict | None = None,
) -> int:
    """为账套新建并绑定一个套餐；额度为 0 表示该项不限制。"""
    with app.state.control_session_factory() as control:
        tenant = find_tenant(control, slug)
        assert tenant is not None, slug
        plan = Plan(
            code=f"{code}-{slug}",
            name=name,
            max_users=max_users,
            max_storage_mb=max_storage_mb,
            max_expenses_per_month=max_expenses_per_month,
            features=features or {},
        )
        control.add(plan)
        control.flush()
        tenant.plan_id = plan.id
        control.commit()
        return plan.id


def update_tenant(
    app: Any, slug: str, *, status: str | None = None, expires_on: date | None = None
) -> None:
    """模拟运营后台改状态或到期日（改完立即生效，不需要重启）。"""
    with app.state.control_session_factory() as control:
        tenant = find_tenant(control, slug)
        assert tenant is not None, slug
        if status is not None:
            tenant.status = status
        if expires_on is not None:
            tenant.expires_on = expires_on
        control.commit()


def fetch_quota(client, headers: dict[str, str] | None = None) -> dict:
    response = client.get("/api/quota", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def tenant_library_dir(settings, slug: str):
    """该账套的文件库目录（存储用量按它累计）。"""
    return settings.for_tenant(slug).library_dir


def fill_library(settings, slug: str, megabytes: int, name: str = "big.bin") -> None:
    """在文件库里写入指定大小的文件，用来把存储用量顶到上限之上。"""
    directory = tenant_library_dir(settings, slug)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_bytes(b"0" * (megabytes * 1024 * 1024))
