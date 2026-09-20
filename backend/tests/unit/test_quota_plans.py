"""套餐额度解析：绑定套餐时用套餐，未绑定时回落到内置免费套餐，0 表示不限制。"""

import pytest

from invoice_sorting.config import Settings
from invoice_sorting.control.database import (
    create_control_engine,
    init_control_db,
    make_control_session_factory,
)
from invoice_sorting.control.models import Plan, Tenant
from invoice_sorting.control.repository import create_tenant
from invoice_sorting.quota.plans import (
    FREE_PLAN,
    ensure_default_plan,
    is_unlimited,
    limit_of,
    resolve_limits,
)


@pytest.fixture
def control(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    engine = create_control_engine(settings)
    init_control_db(engine)
    factory = make_control_session_factory(engine)
    try:
        with factory() as db:
            yield db
    finally:
        engine.dispose()


def test_tenant_without_plan_falls_back_to_free_plan(control):
    tenant = create_tenant(control, "alpha", "阿尔法")

    assert resolve_limits(control, tenant) == FREE_PLAN


def test_tenant_with_plan_uses_its_limits(control):
    plan = Plan(code="team", name="团队版", max_users=20, max_storage_mb=50, features={"ocr": True})
    control.add(plan)
    control.flush()
    tenant = create_tenant(control, "alpha", "阿尔法", plan_id=plan.id)

    limits = resolve_limits(control, tenant)

    assert (limits.code, limits.name, limits.max_users) == ("team", "团队版", 20)
    assert limits.max_storage_mb == 50
    assert limits.features == {"ocr": True}


def test_missing_plan_row_falls_back_instead_of_failing(control):
    """套餐被删掉的历史数据不应让请求失败。"""
    tenant = Tenant(slug="alpha", name="阿尔法", plan_id=999)

    assert resolve_limits(control, tenant) == FREE_PLAN


def test_default_free_plan_is_seeded_idempotently(control):
    first = ensure_default_plan(control)
    second = ensure_default_plan(control)

    assert first.id == second.id
    assert (first.code, first.max_users) == (FREE_PLAN.code, FREE_PLAN.max_users)
    assert control.query(Plan).count() == 1


def test_zero_limit_means_unlimited():
    assert is_unlimited(0) is True
    assert is_unlimited(-1) is True
    assert is_unlimited(1) is False


def test_limit_of_reads_the_matching_field():
    assert limit_of(FREE_PLAN, "users") == FREE_PLAN.max_users
    assert limit_of(FREE_PLAN, "storage") == FREE_PLAN.max_storage_mb
    assert limit_of(FREE_PLAN, "expenses") == FREE_PLAN.max_expenses_per_month
    assert limit_of(FREE_PLAN, "unknown") == 0
