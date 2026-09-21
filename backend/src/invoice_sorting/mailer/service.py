"""发信服务：未配置时跳过；失败有重试上限，只返回脱敏后的中文原因。

发送失败**不抛异常**——审批结果已经生效，调用方把结果记下来、后台可「重新发送」。
错误文案只按异常类型给出固定说明，不拼接服务器原文（原文可能回显账号等信息）。

配置不在这里决定：由 `mailer/resolve.py` 按「环境变量 → 网页配置 → 未配置」解析后传入，
每次请求按当时生效的配置现造一个 `Mailer`（网页上改完即生效，无需重启）。
"""

import logging
import smtplib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

from invoice_sorting.mailer.errors import (
    MSG_SERVER_REFUSED,
    MSG_TIMEOUT,
    MSG_UNKNOWN,
    describe_error,
)
from invoice_sorting.mailer.transport import (
    MailTransport,
    SmtpConfig,
    SmtplibTransport,
    TransportFactory,
)

__all__ = [
    "MSG_SERVER_REFUSED",
    "MSG_TIMEOUT",
    "MailConfig",
    "Mailer",
    "MailerFactory",
    "describe_error",
]

logger = logging.getLogger(__name__)

STATE_MAILER_KEY = "mailer"
MAX_ATTEMPTS = 2  # 首次 + 重试 1 次
RETRY_DELAY_SECONDS = 1.0

RESULT_SENT = "sent"
RESULT_FAILED = "failed"
RESULT_SKIPPED = "skipped"

# 这些错误重试也不会好，直接放弃
_PERMANENT_ERRORS = (
    smtplib.SMTPAuthenticationError,
    smtplib.SMTPRecipientsRefused,
    smtplib.SMTPSenderRefused,
)


@dataclass(frozen=True)
class MailConfig:
    """一套可用的发信配置。password_error 非空表示密码无法解密，只能提示重新填写。"""

    smtp: SmtpConfig
    sender: str
    password_error: str = ""


@dataclass(frozen=True)
class MailResult:
    status: str
    error: str = ""

    @property
    def is_sent(self) -> bool:
        return self.status == RESULT_SENT


def sender_domain(sender: str) -> str:
    address = parseaddr(sender)[1]
    return address.rpartition("@")[2] or "localhost"


def compose(sender: str, to: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    # 显式给出域名：不给时 make_msgid 会查询本机 FQDN（可能触发 DNS）
    message["Message-ID"] = make_msgid(domain=sender_domain(sender))
    message.set_content(body)
    return message


class Mailer:
    def __init__(
        self,
        config: MailConfig | None,
        transport: MailTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._config = config
        self._transport = transport
        if config is not None and transport is None:
            self._transport = SmtplibTransport(config.smtp)
        self._sleep = sleep

    @property
    def is_configured(self) -> bool:
        return self._config is not None

    def send(self, to: str, subject: str, body: str) -> MailResult:
        if self._config is None or self._transport is None:
            return MailResult(status=RESULT_SKIPPED)
        if self._config.password_error:
            return MailResult(status=RESULT_FAILED, error=self._config.password_error)
        message = compose(self._config.sender, to, subject, body)
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


@dataclass(frozen=True)
class MailerFactory:
    """按当时生效的配置造发信服务；测试替换 transport_factory，绝不真实联网。"""

    transport_factory: TransportFactory = field(default=SmtplibTransport)
    sleep: Callable[[float], None] = field(default=time.sleep)

    def transport(self, config: MailConfig) -> MailTransport:
        return self.transport_factory(config.smtp)

    def build(self, config: MailConfig | None) -> Mailer:
        transport = self.transport(config) if config is not None else None
        return Mailer(config, transport=transport, sleep=self.sleep)
