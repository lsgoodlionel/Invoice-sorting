"""注册申请测试辅助：内存发信（绝不联网）、已装配的多账套应用、常用请求。"""

import re
from email.message import EmailMessage
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from invoice_sorting.auth.ratelimit import LoginRateLimiter
from invoice_sorting.control.signup_models import SignupApplication
from invoice_sorting.mailer.service import STATE_MAILER_KEY, Mailer
from invoice_sorting.signup.deps import STATE_APPLY_LIMITER
from tests.platform_helpers import platform_app

SMTP_PASSWORD = "S3cret-Smtp-Pw!9"
BASE_URL = "https://fp.example.com"
SMTP_SETTINGS = {
    "smtp_host": "smtp.invalid",  # 保留域名：即使误用真实传输也不会连到任何服务器
    "smtp_port": 465,
    "smtp_user": "mailer",
    "smtp_password": SMTP_PASSWORD,
    "smtp_from": "发票报销 <noreply@fp.example.com>",
    "public_base_url": BASE_URL,
}
APPLICATIONS = "/api/signup/applications"
REGISTER = "/api/signup/register"
PLATFORM_APPLICATIONS = "/api/platform/applications"
SETTINGS_PATH = "/api/platform/signup-settings"
LINK_PATTERN = re.compile(r"/register\?code=([A-Za-z0-9_\-%]+)")


class FakeTransport:
    """记录每一封信；errors 非空时按顺序抛出（用完后正常发送）。"""

    def __init__(self, errors: list[BaseException] | None = None) -> None:
        self.messages: list[EmailMessage] = []
        self.errors = list(errors or [])

    def send(self, message: EmailMessage) -> None:
        if self.errors:
            raise self.errors.pop(0)
        self.messages.append(message)

    def last_body(self) -> str:
        return self.messages[-1].get_content()


def install_transport(app: Any, transport: FakeTransport) -> FakeTransport:
    mailer = Mailer(app.state.settings, transport=transport, sleep=lambda _seconds: None)
    setattr(app.state, STATE_MAILER_KEY, mailer)
    return transport


def signup_app(tmp_path, *, with_smtp: bool = True, **overrides):
    """平台应用（alpha/beta/platform 三个账套）；with_smtp 时换上内存发信。"""
    extra = {**(SMTP_SETTINGS if with_smtp else {}), **overrides}
    app = platform_app(tmp_path, **extra)
    install_transport(app, FakeTransport())
    return app


def transport_of(app: Any) -> FakeTransport:
    return getattr(app.state, STATE_MAILER_KEY)._transport


def relax_apply_limit(app: Any) -> None:
    setattr(app.state, STATE_APPLY_LIMITER, LoginRateLimiter(max_failures=1000))


def apply_body(email: str = "zhang@example.org", **overrides) -> dict[str, Any]:
    body = {
        "name": "张三",
        "email": email,
        "identity": "某某大学 财务处",
        "needs": "课题组报销票据整理",
        "ledger_name": "张三课题组",
    }
    return {**body, **overrides}


def apply(client: TestClient, email: str = "zhang@example.org", **overrides):
    return client.post(APPLICATIONS, json=apply_body(email, **overrides))


def submit_ok(client: TestClient, email: str = "zhang@example.org", **overrides) -> dict:
    response = apply(client, email, **overrides)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def code_from(text: str) -> str:
    match = LINK_PATTERN.search(text)
    assert match is not None, text
    return match.group(1)


def approve(platform: TestClient, application_id: int, **body) -> dict:
    response = platform.post(f"{PLATFORM_APPLICATIONS}/{application_id}/approve", json=body)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def register_body(code: str, email: str = "zhang@example.org", **overrides) -> dict[str, Any]:
    body = {"code": code, "email": email, "username": "zhangsan", "password": "zhang-pass-123"}
    return {**body, **overrides}


def application_rows(app: Any) -> list[SignupApplication]:
    with app.state.control_session_factory() as control:
        return list(control.scalars(select(SignupApplication).order_by(SignupApplication.id)))


def update_application(app: Any, application_id: int, **values) -> None:
    with app.state.control_session_factory() as control:
        row = control.get(SignupApplication, application_id)
        for key, value in values.items():
            setattr(row, key, value)
        control.commit()
