"""内置测试公钥的私钥是公开的：状态接口要如实报告，启用授权校验时要告警。"""

import logging

from invoice_sorting.licensing.keys import (
    DEFAULT_PUBLIC_KEY_B64,
    ENV_PUBLIC_KEY,
    is_test_public_key,
)
from invoice_sorting.licensing.serializers import serialize_status
from invoice_sorting.licensing.state import LicenseStatus
from invoice_sorting.main import create_app
from tests.conftest import make_settings

OTHER_PUBLIC_KEY = "2S1p3QOlPSdSbe6t4v7lJ4HcfPHcT9lY9lWqI9hMOxQ="


def test_builtin_key_is_reported_as_test_key(monkeypatch):
    monkeypatch.delenv(ENV_PUBLIC_KEY, raising=False)

    assert is_test_public_key() is True


def test_own_key_is_not_reported_as_test_key(monkeypatch):
    monkeypatch.setenv(ENV_PUBLIC_KEY, OTHER_PUBLIC_KEY)

    assert is_test_public_key() is False


def test_unparsable_key_falls_back_to_builtin(monkeypatch):
    monkeypatch.setenv(ENV_PUBLIC_KEY, "不是 base64")

    assert is_test_public_key() is True


def test_status_exposes_the_flag(monkeypatch):
    monkeypatch.setenv(ENV_PUBLIC_KEY, DEFAULT_PUBLIC_KEY_B64)

    assert serialize_status(LicenseStatus(state="active", message=""))["uses_test_key"] is True


def test_startup_warns_when_license_enabled_with_test_key(tmp_path, monkeypatch, caplog):
    monkeypatch.delenv(ENV_PUBLIC_KEY, raising=False)
    settings = make_settings(
        tmp_path, license_key="demo-key", license_server="https://例子.invalid"
    )

    with caplog.at_level(logging.WARNING):
        create_app(settings)

    assert any("测试授权公钥" in record.message for record in caplog.records)
