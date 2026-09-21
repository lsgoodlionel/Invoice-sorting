"""平台邮件设置测试辅助：未配置 SMTP 环境变量的平台应用、已登录客户端、常用请求体。"""

from typing import Any

from fastapi.testclient import TestClient

from invoice_sorting.control.mail_models import MAIL_SETTINGS_ROW_ID, MailSettings
from tests.platform_helpers import login_platform
from tests.signup_helpers import FakeTransport, install_transport, signup_app

MAIL_PATH = "/api/platform/mail-settings"
TEST_CONNECTION = f"{MAIL_PATH}/test-connection"
TEST_EMAIL = f"{MAIL_PATH}/test-email"
WEB_PASSWORD = "Web-Auth-Code-7788"
WEB_BODY = {
    "host": "smtp.invalid",  # 保留域名：即使误用真实传输也不会连到任何服务器
    "port": 465,
    "tls": "ssl",
    "username": "robot@fp.example.com",
    "password": WEB_PASSWORD,
    "sender": "发票报销 <robot@fp.example.com>",
    "public_base_url": "https://web.example.com",
}


def web_app(tmp_path, **overrides):
    """不带 SMTP 环境变量的平台应用，换上内存发信。"""
    return signup_app(tmp_path, with_smtp=False, **overrides)


def fresh_transport(app: Any, errors: list[BaseException] | None = None) -> FakeTransport:
    return install_transport(app, FakeTransport(errors))


def save(client: TestClient, **overrides) -> dict[str, Any]:
    response = client.patch(MAIL_PATH, json={**WEB_BODY, **overrides})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def platform_client(app: Any) -> TestClient:
    return login_platform(app)


def mail_row(app: Any) -> MailSettings | None:
    with app.state.control_session_factory() as control:
        row = control.get(MailSettings, MAIL_SETTINGS_ROW_ID)
        if row is not None:
            control.expunge(row)
        return row
