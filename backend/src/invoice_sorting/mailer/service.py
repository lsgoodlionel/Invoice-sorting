"""发信服务：未配置时跳过；失败有重试上限，只返回脱敏后的中文原因。

发送失败**不抛异常**——审批结果已经生效，调用方把结果记下来、后台可「重新发送」。
错误文案只按异常类型给出固定说明，不拼接服务器原文（原文可能回显账号等信息）。
"""

import logging
import smtplib
import time
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

from invoice_sorting.config import Settings
from invoice_sorting.mailer.transport import MailTransport, SmtpConfig, SmtplibTransport

logger = logging.getLogger(__name__)

STATE_MAILER_KEY = "mailer"
MAX_ATTEMPTS = 2  # 首次 + 重试 1 次
RETRY_DELAY_SECONDS = 1.0

RESULT_SENT = "sent"
RESULT_FAILED = "failed"
RESULT_SKIPPED = "skipped"

MSG_AUTH_FAILED = "邮件服务器登录失败，请检查 SMTP 用户名与密码配置"
MSG_RECIPIENT_REFUSED = "收件地址被邮件服务器拒收"
MSG_SENDER_REFUSED = "发件地址被邮件服务器拒绝，请检查 SMTP_FROM 配置"
MSG_TIMEOUT = "连接邮件服务器超时"
MSG_CONNECT_FAILED = "无法连接邮件服务器"
MSG_SERVER_REFUSED = "邮件服务器拒绝了本次发送（代码 {code}）"
MSG_UNKNOWN = "邮件发送失败"

# 这些错误重试也不会好，直接放弃
_PERMANENT_ERRORS = (
    smtplib.SMTPAuthenticationError,
    smtplib.SMTPRecipientsRefused,
    smtplib.SMTPSenderRefused,
)


@dataclass(frozen=True)
class MailResult:
    status: str
    error: str = ""

    @property
    def is_sent(self) -> bool:
        return self.status == RESULT_SENT


def describe_error(error: BaseException) -> str:
    """把异常翻译成固定的中文说明；绝不带出异常原文。"""
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return MSG_AUTH_FAILED
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        return MSG_RECIPIENT_REFUSED
    if isinstance(error, smtplib.SMTPSenderRefused):
        return MSG_SENDER_REFUSED
    if isinstance(error, smtplib.SMTPResponseException):
        return MSG_SERVER_REFUSED.format(code=error.smtp_code)
    if isinstance(error, TimeoutError):
        return MSG_TIMEOUT
    if isinstance(error, (smtplib.SMTPException, OSError)):
        return MSG_CONNECT_FAILED
    return MSG_UNKNOWN


def _sender_domain(sender: str) -> str:
    address = parseaddr(sender)[1]
    return address.rpartition("@")[2] or "localhost"


class Mailer:
    def __init__(
        self,
        settings: Settings,
        transport: MailTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._sender = settings.smtp_from.strip()
        self._is_configured = settings.is_smtp_configured
        self._transport = transport or SmtplibTransport(SmtpConfig.from_settings(settings))
        self._sleep = sleep

    @property
    def is_configured(self) -> bool:
        return self._is_configured

    def send(self, to: str, subject: str, body: str) -> MailResult:
        if not self._is_configured:
            return MailResult(status=RESULT_SKIPPED)
        message = self._compose(to, subject, body)
        error: BaseException | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                self._transport.send(message)
                return MailResult(status=RESULT_SENT)
            except Exception as exc:  # noqa: BLE001 - 发信失败只记录，不影响业务结果
                error = exc
                if isinstance(exc, _PERMANENT_ERRORS) or attempt == MAX_ATTEMPTS:
                    break
                self._sleep(RETRY_DELAY_SECONDS)
        reason = describe_error(error) if error is not None else MSG_UNKNOWN
        logger.warning("通知邮件发送失败：%s（%s）", reason, type(error).__name__)
        return MailResult(status=RESULT_FAILED, error=reason)

    def _compose(self, to: str, subject: str, body: str) -> EmailMessage:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to
        message["Subject"] = subject
        message["Date"] = formatdate(localtime=True)
        # 显式给出域名：不给时 make_msgid 会查询本机 FQDN（可能触发 DNS）
        message["Message-ID"] = make_msgid(domain=_sender_domain(self._sender))
        message.set_content(body)
        return message
