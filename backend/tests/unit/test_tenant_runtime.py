"""租户运行时：按 slug 缓存引擎与会话工厂，超出容量按最近最少使用驱逐。"""

import pytest
from sqlalchemy import select

from invoice_sorting.config import Settings
from invoice_sorting.db.models import Category
from invoice_sorting.tenancy.runtime import TenantRuntime


@pytest.fixture
def base_settings(tmp_path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        deployment_mode="saas",
        open_browser=False,
        watch_inbox=False,
        auth_enabled=False,
    )


def test_first_access_creates_dirs_db_and_seed(base_settings):
    runtime = TenantRuntime(base_settings)
    try:
        context = runtime.get("alpha")

        assert context.settings.data_dir == base_settings.data_dir / "tenants" / "alpha"
        assert context.settings.db_path.exists()
        assert context.settings.library_dir.is_dir()
        with context.session_factory() as db:
            assert db.scalars(select(Category)).first() is not None
    finally:
        runtime.close()


def test_same_slug_returns_cached_context(base_settings):
    runtime = TenantRuntime(base_settings)
    try:
        assert runtime.get("alpha") is runtime.get("alpha")
        assert runtime.cached_slugs() == ("alpha",)
    finally:
        runtime.close()


def test_capacity_evicts_least_recently_used(base_settings):
    runtime = TenantRuntime(base_settings, capacity=2)
    try:
        first = runtime.get("alpha")
        runtime.get("beta")
        runtime.get("alpha")  # alpha 变为最近使用
        runtime.get("gamma")  # 触发驱逐，应淘汰 beta

        assert runtime.cached_slugs() == ("alpha", "gamma")
        assert runtime.get("alpha") is first  # alpha 仍在缓存中
    finally:
        runtime.close()


def test_evict_disposes_and_reopens(base_settings):
    runtime = TenantRuntime(base_settings)
    try:
        first = runtime.get("alpha")

        assert runtime.evict("alpha") is True
        assert runtime.evict("alpha") is False
        assert runtime.cached_slugs() == ()

        second = runtime.get("alpha")
        assert second is not first
        assert second.settings.data_dir == first.settings.data_dir
    finally:
        runtime.close()


def test_close_clears_cache(base_settings):
    runtime = TenantRuntime(base_settings)
    runtime.get("alpha")
    runtime.get("beta")

    runtime.close()

    assert runtime.cached_slugs() == ()


def test_capacity_must_be_positive(base_settings):
    with pytest.raises(ValueError):
        TenantRuntime(base_settings, capacity=0)


def test_tenants_do_not_share_data(base_settings):
    runtime = TenantRuntime(base_settings)
    try:
        alpha = runtime.get("alpha")
        beta = runtime.get("beta")
        with alpha.session_factory() as db:
            db.add(Category(name="只属于 alpha"))
            db.commit()

        with beta.session_factory() as db:
            found = db.scalar(select(Category).where(Category.name == "只属于 alpha"))

        assert found is None
    finally:
        runtime.close()
