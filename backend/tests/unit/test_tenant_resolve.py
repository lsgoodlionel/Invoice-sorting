"""租户解析：子域名优先，其次请求状态，单租户模式固定 default，其余一律报错。"""

import pytest

from invoice_sorting.common.errors import AppError
from invoice_sorting.config import DEFAULT_TENANT_SLUG, Settings
from invoice_sorting.tenancy.resolve import (
    STATE_TENANT_KEY,
    resolve_tenant_slug,
    slug_from_host,
)


class _Conn:
    """最小的连接替身：只需要 headers 与 scope state。"""

    def __init__(self, host: str = "", state: dict | None = None) -> None:
        self.headers = {"host": host} if host else {}
        self.scope = {"state": state or {}}


def _settings(tmp_path, **overrides) -> Settings:
    return Settings(data_dir=tmp_path / "data", **overrides)


@pytest.mark.parametrize(
    ("host", "suffix", "expected"),
    [
        ("t1.example.com", "example.com", "t1"),
        ("T1.Example.com:8765", "example.com", "t1"),
        ("t1.example.com", ".example.com", "t1"),
        ("example.com", "example.com", None),  # 裸域名不是租户
        ("a.b.example.com", "example.com", None),  # 只接受一级子域名
        ("t1.other.com", "example.com", None),
        ("t1.example.com", "", None),  # 未配置后缀时不解析子域名
        ("", "example.com", None),
    ],
)
def test_slug_from_host(host, suffix, expected):
    assert slug_from_host(host, suffix) == expected


def test_single_mode_always_resolves_to_default(tmp_path):
    settings = _settings(tmp_path, tenant_host_suffix="example.com")

    slug = resolve_tenant_slug(settings, _Conn(host="t1.example.com"))

    assert slug == DEFAULT_TENANT_SLUG


def test_saas_mode_uses_subdomain(tmp_path):
    settings = _settings(tmp_path, deployment_mode="saas", tenant_host_suffix="example.com")

    assert resolve_tenant_slug(settings, _Conn(host="t1.example.com")) == "t1"


def test_saas_mode_falls_back_to_request_state(tmp_path):
    settings = _settings(tmp_path, deployment_mode="saas", tenant_host_suffix="example.com")
    conn = _Conn(host="example.com", state={STATE_TENANT_KEY: "beta"})

    assert resolve_tenant_slug(settings, conn) == "beta"


def test_saas_mode_without_any_hint_raises(tmp_path):
    settings = _settings(tmp_path, deployment_mode="saas")

    with pytest.raises(AppError) as excinfo:
        resolve_tenant_slug(settings, _Conn(host="example.com"))

    assert excinfo.value.status_code == 400
    assert "账套" in excinfo.value.message


@pytest.mark.parametrize("bad", ["../../etc", "有中文", "-", "a" * 60])
def test_saas_mode_rejects_malformed_slug_from_state(tmp_path, bad):
    settings = _settings(tmp_path, deployment_mode="saas")
    conn = _Conn(state={STATE_TENANT_KEY: bad})

    with pytest.raises(AppError) as excinfo:
        resolve_tenant_slug(settings, conn)

    assert excinfo.value.status_code == 400
