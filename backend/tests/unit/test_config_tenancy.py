"""配置的租户派生：单租户模式沿用原 data_dir，SaaS 模式按 slug 分目录。"""

from pathlib import Path

from invoice_sorting.config import DEFAULT_TENANT_SLUG, Settings


def _settings(tmp_path: Path, **overrides) -> Settings:
    return Settings(data_dir=tmp_path / "data", **overrides)


def test_default_deployment_mode_is_single(tmp_path):
    assert _settings(tmp_path).deployment_mode == "single"
    assert _settings(tmp_path).is_saas is False


def test_control_db_sits_in_data_dir_root(tmp_path):
    settings = _settings(tmp_path)

    assert settings.control_db_path == tmp_path / "data" / "control.db"


def test_single_mode_default_tenant_keeps_legacy_data_dir(tmp_path):
    settings = _settings(tmp_path)

    derived = settings.for_tenant(DEFAULT_TENANT_SLUG)

    assert derived.data_dir == settings.data_dir
    assert derived.db_path == settings.data_dir / "invoice.db"


def test_saas_mode_default_tenant_uses_subdirectory(tmp_path):
    settings = _settings(tmp_path, deployment_mode="saas")

    derived = settings.for_tenant(DEFAULT_TENANT_SLUG)

    assert derived.data_dir == settings.data_dir / "tenants" / "default"


def test_tenant_settings_are_new_objects_and_keep_other_fields(tmp_path):
    settings = _settings(tmp_path, deployment_mode="saas", port=9999, auth_enabled=False)

    derived = settings.for_tenant("alpha")

    assert derived is not settings
    assert settings.data_dir == tmp_path / "data"  # 原配置未被修改
    assert derived.port == 9999
    assert derived.auth_enabled is False
    assert derived.deployment_mode == "saas"


def test_two_tenants_get_separate_directories(tmp_path):
    settings = _settings(tmp_path, deployment_mode="saas")

    alpha = settings.for_tenant("alpha")
    beta = settings.for_tenant("beta")

    assert alpha.data_dir != beta.data_dir
    assert alpha.library_dir != beta.library_dir
    assert alpha.db_path != beta.db_path
