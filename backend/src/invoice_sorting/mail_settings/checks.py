"""测试连接与测试邮件：不重试、不带服务器原文，只返回分类后的中文结果。"""

from dataclasses import dataclass

from invoice_sorting.mail_settings.constants import (
    MSG_CONNECTION_OK,
    MSG_CONNECTION_OK_NO_AUTH,
    MSG_EMAIL_OK,
    TEST_BODY,
    TEST_SUBJECT,
)
from invoice_sorting.mailer.errors import CATEGORY_OK, CATEGORY_PASSWORD, ErrorInfo, classify_error
from invoice_sorting.mailer.service import MailConfig, MailerFactory, compose


@dataclass(frozen=True)
class CheckOutcome:
    is_ok: bool
    info: ErrorInfo


def _failed(error: BaseException) -> CheckOutcome:
    return CheckOutcome(is_ok=False, info=classify_error(error))


def _password_problem(config: MailConfig) -> CheckOutcome | None:
    if not config.password_error:
        return None
    return CheckOutcome(is_ok=False, info=ErrorInfo(CATEGORY_PASSWORD, config.password_error))


def check_connection(factory: MailerFactory, config: MailConfig) -> CheckOutcome:
    """连接并登录，不发信。"""
    problem = _password_problem(config)
    if problem is not None:
        return problem
    try:
        factory.transport(config).check()
    except Exception as error:  # noqa: BLE001 - 所有失败都分类后返回给页面
        return _failed(error)
    message = MSG_CONNECTION_OK if config.smtp.user else MSG_CONNECTION_OK_NO_AUTH
    return CheckOutcome(is_ok=True, info=ErrorInfo(CATEGORY_OK, message))


def send_test_email(factory: MailerFactory, config: MailConfig, to: str) -> CheckOutcome:
    problem = _password_problem(config)
    if problem is not None:
        return problem
    message = compose(config.sender, to, TEST_SUBJECT, TEST_BODY)
    try:
        factory.transport(config).send(message)
    except Exception as error:  # noqa: BLE001 - 所有失败都分类后返回给页面
        return _failed(error)
    return CheckOutcome(is_ok=True, info=ErrorInfo(CATEGORY_OK, MSG_EMAIL_OK))
