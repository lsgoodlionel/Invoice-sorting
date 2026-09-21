"""网页邮件配置生效：注册审批发信改用解析后的配置；密钥文件不进搬迁包与诊断包。"""

import zipfile

import pytest
from fastapi.testclient import TestClient

from invoice_sorting.common.secret_box import encrypt_secret
from invoice_sorting.config import SECRET_KEY_FILENAME
from invoice_sorting.diagnostics.collect import collect_package
from invoice_sorting.diagnostics.constants import ENV_SET, MEMBER_ENV, REASON_MANUAL
from invoice_sorting.migration.export import export_tenant
from tests.diagnostics_helpers import FIXED_TIME, package_members, stub_commands
from tests.mail_helpers import WEB_PASSWORD, fresh_transport, platform_client, save, web_app
from tests.signup_helpers import (
    SETTINGS_PATH,
    application_rows,
    approve,
    code_from,
    relax_apply_limit,
    signup_app,
    submit_ok,
)


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.delenv("INVOICE_SORTING_SECRET_KEY", raising=False)
    app = web_app(tmp_path)
    relax_apply_limit(app)
    return app


def test_without_any_config_approval_mail_is_skipped(app):
    platform = platform_client(app)
    transport = fresh_transport(app)
    application_id = submit_ok(TestClient(app))["id"]

    data = approve(platform, application_id)

    assert data["notice"]["mail_status"] == "skipped" and transport.messages == []
    assert platform.get(SETTINGS_PATH).json()["data"]["is_mail_configured"] is False


def test_web_config_is_used_for_approval_mail(app):
    platform = platform_client(app)
    save(platform)
    transport = fresh_transport(app)
    application_id = submit_ok(TestClient(app))["id"]

    data = approve(platform, application_id)

    assert data["notice"]["mail_status"] == "sent"
    assert transport.configs[-1].password == WEB_PASSWORD
    assert "robot@fp.example.com" in transport.messages[0]["From"]
    assert "https://web.example.com/register?code=" in transport.last_body()
    assert code_from(transport.last_body())
    assert platform.get(SETTINGS_PATH).json()["data"]["is_mail_configured"] is True


def test_lost_key_marks_mail_failed_with_refill_hint(app):
    platform = platform_client(app)
    save(platform)
    transport = fresh_transport(app)
    (app.state.settings.data_dir / SECRET_KEY_FILENAME).unlink()
    application_id = submit_ok(TestClient(app))["id"]

    data = approve(platform, application_id)

    assert data["notice"]["mail_status"] == "failed"
    assert "请重新填写 SMTP 密码" in data["notice"]["mail_error"]
    assert transport.messages == [] and application_rows(app)[0].mail_status == "failed"


def test_env_config_wins_over_saved_web_config(tmp_path):
    app = signup_app(tmp_path)
    relax_apply_limit(app)
    platform = platform_client(app)
    transport = fresh_transport(app)
    application_id = submit_ok(TestClient(app))["id"]

    approve(platform, application_id)

    assert transport.configs[-1].host == "smtp.invalid" and transport.configs[-1].user == "mailer"
    assert "https://fp.example.com/register?code=" in transport.last_body()


def test_referral_link_uses_web_base_url(app):
    platform = platform_client(app)
    save(platform)

    link = platform.get("/api/referrals/me").json()["data"]["link"]

    assert link.startswith("https://web.example.com/apply?ref=")


def test_single_tenant_export_never_contains_secret_key(settings, tmp_path):
    from invoice_sorting.main import create_app

    app = create_app(settings)
    encrypt_secret(settings, "x")  # 单账套 default 账本目录即 data_dir，密钥文件与账本同目录
    assert settings.secret_key_path.exists()

    result = export_tenant(app.state.tenants.get("default"), tmp_path / "out.zip")

    with zipfile.ZipFile(result.path) as archive:
        names = archive.namelist()
    assert all(SECRET_KEY_FILENAME not in name for name in names)
    assert all(entry.path != SECRET_KEY_FILENAME for entry in result.manifest.files)


def test_diagnostics_package_never_contains_secret_key(tmp_path, monkeypatch):
    stub_commands(monkeypatch)
    monkeypatch.delenv("INVOICE_SORTING_SECRET_KEY", raising=False)
    app = web_app(tmp_path)
    save(platform_client(app))
    settings = app.state.settings
    key = settings.secret_key_path.read_text().strip()
    settings.logs_dir.mkdir(parents=True, exist_ok=True)

    result = collect_package(settings, REASON_MANUAL, FIXED_TIME)

    members = package_members(result.path)
    assert all(SECRET_KEY_FILENAME not in name for name in members)
    assert all(key not in content and WEB_PASSWORD not in content for content in members.values())


def test_diagnostics_env_lists_secret_key_presence_only(tmp_path, monkeypatch):
    stub_commands(monkeypatch)
    key = "k" * 44
    monkeypatch.setenv("INVOICE_SORTING_SECRET_KEY", key)
    app = web_app(tmp_path)
    settings = app.state.settings
    settings.logs_dir.mkdir(parents=True, exist_ok=True)

    members = package_members(collect_package(settings, REASON_MANUAL, FIXED_TIME).path)

    assert f"INVOICE_SORTING_SECRET_KEY  {ENV_SET}" in members[MEMBER_ENV]
    assert all(key not in content for content in members.values())
