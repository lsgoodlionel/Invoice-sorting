"""平台邮件设置接口：读取不含密码、保存校验、密码“不改/清除”语义、环境变量优先、权限边界。"""

import logging

import pytest
from fastapi.testclient import TestClient

from invoice_sorting.config import SECRET_KEY_FILENAME
from tests.mail_helpers import (
    MAIL_PATH,
    TEST_CONNECTION,
    TEST_EMAIL,
    WEB_BODY,
    WEB_PASSWORD,
    mail_row,
    platform_client,
    save,
    web_app,
)
from tests.platform_helpers import PLATFORM_ADMIN
from tests.signup_helpers import SMTP_PASSWORD, signup_app
from tests.tenancy_helpers import login_at


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.delenv("INVOICE_SORTING_SECRET_KEY", raising=False)
    return web_app(tmp_path)


@pytest.fixture
def platform(app):
    return platform_client(app)


def test_get_defaults_when_nothing_configured(platform):
    data = platform.get(MAIL_PATH).json()["data"]

    assert data["source"] == "none" and not data["is_configured"]
    assert (data["host"], data["port"], data["tls"]) == ("", 465, "ssl")
    assert not data["password_set"] and data["last_check"] is None


def test_save_encrypts_password_and_never_returns_it(app, platform, caplog):
    with caplog.at_level(logging.DEBUG):
        saved = save(platform)
        read = platform.get(MAIL_PATH)

    row = mail_row(app)
    assert row is not None and row.password_encrypted
    assert WEB_PASSWORD not in row.password_encrypted
    for text in (str(saved), read.text):
        assert WEB_PASSWORD not in text and row.password_encrypted not in text
        assert "password_encrypted" not in text
    assert WEB_PASSWORD not in caplog.text
    data = read.json()["data"]
    assert data["source"] == "web" and data["is_configured"] and data["password_set"]
    assert data["updated_by"] == PLATFORM_ADMIN and data["updated_at"]
    assert data["public_base_url"] == "https://web.example.com"
    assert (app.state.settings.data_dir / SECRET_KEY_FILENAME).exists()


def test_password_omitted_or_null_keeps_existing(app, platform):
    save(platform)
    before = mail_row(app).password_encrypted

    platform.patch(MAIL_PATH, json={"port": 587, "tls": "starttls"})
    platform.patch(MAIL_PATH, json={"password": None})

    row = mail_row(app)
    assert row.password_encrypted == before and (row.port, row.tls) == (587, "starttls")


def test_empty_password_clears_it(app, platform):
    save(platform)

    data = platform.patch(MAIL_PATH, json={"password": ""}).json()["data"]

    assert not data["password_set"] and mail_row(app).password_encrypted == ""


@pytest.mark.parametrize(
    "body",
    [
        {"host": "bad host"},
        {"port": 70000},
        {"sender": "nobody"},
        {"public_base_url": "javascript:alert(1)"},
        {"tls": "ssl3"},
    ],
)
def test_patch_validation_errors_are_422(platform, body):
    response = platform.patch(MAIL_PATH, json=body)

    assert response.status_code == 422
    assert response.json()["error"].startswith("参数错误")


def test_env_config_takes_priority_and_is_read_only(tmp_path):
    app = signup_app(tmp_path)  # 带 SMTP 环境变量配置
    platform = platform_client(app)

    data = platform.get(MAIL_PATH).json()["data"]
    response = platform.patch(MAIL_PATH, json=WEB_BODY)

    assert data["source"] == "env" and data["host"] == "smtp.invalid"
    assert data["password_set"] and SMTP_PASSWORD not in str(data)
    assert response.status_code == 409
    assert response.json()["error"] == "邮件由服务器环境变量配置，网页上不能修改"
    assert mail_row(app) is None


def test_unreadable_password_shows_hint_instead_of_500(app, platform):
    save(platform)
    (app.state.settings.data_dir / SECRET_KEY_FILENAME).unlink()

    response = platform.get(MAIL_PATH)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["password_set"] and "请重新填写 SMTP 密码" in data["password_error"]


def test_refilling_password_after_key_loss_recovers(app, platform):
    save(platform)
    (app.state.settings.data_dir / SECRET_KEY_FILENAME).unlink()

    data = save(platform, password="new-auth-code")

    assert data["password_error"] == "" and data["password_set"]


@pytest.fixture
def tenant_admin(app):
    client = TestClient(app)
    assert login_at(client, "alpha-admin", slug="alpha").status_code == 200
    return client


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", MAIL_PATH, None),
        ("patch", MAIL_PATH, WEB_BODY),
        ("post", TEST_CONNECTION, None),
        ("post", TEST_EMAIL, {"to": "a@example.org"}),
    ],
)
def test_non_platform_admin_is_forbidden(tenant_admin, method, path, body):
    kwargs = {"json": body} if body is not None else {}

    response = getattr(tenant_admin, method)(path, **kwargs)

    assert response.status_code == 403


def test_anonymous_is_unauthorized(app):
    assert TestClient(app).get(MAIL_PATH).status_code == 401


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("get", MAIL_PATH, None),
        ("patch", MAIL_PATH, WEB_BODY),
        ("post", TEST_CONNECTION, None),
        ("post", TEST_EMAIL, {"to": "a@example.org"}),
    ],
)
def test_single_tenant_hides_mail_settings(admin_client, method, path, body):
    kwargs = {"json": body} if body is not None else {}

    response = getattr(admin_client, method)(path, **kwargs)

    assert response.status_code == 404
