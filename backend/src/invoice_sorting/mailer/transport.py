"""SMTP 传输层：只负责“连上并登录邮件服务器”与“把一封信交给邮件服务器”。

业务代码只依赖 `MailTransport` 协议，测试替换成内存实现，**绝不真实发信或联网**。
凭证只在建立连接时使用，不写入任何日志与异常文案。
"""

import smtplib
import ssl
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from invoice_sorting.config import SMTP_TLS_SSL, SMTP_TLS_STARTTLS, Settings
from invoice_sorting.mailer.errors import AuthNotSupportedError, StartTLSNotSupportedError

CONNECT_TIMEOUT_SECONDS = 10.0


class MailTransport(Protocol):
    def send(self, message: EmailMessage) -> None: ...

    def check(self) -> None:
        """连接并登录（有用户名时），不发信；失败时抛出原始异常由调用方分类。"""
        ...


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    user: str
    password: str
    tls: str
    timeout: float = CONNECT_TIMEOUT_SECONDS

    def __repr__(self) -> str:  # 防止整体打印时带出密码
        return f"SmtpConfig(host={self.host!r}, port={self.port}, tls={self.tls!r})"

    @classmethod
    def from_settings(cls, settings: Settings) -> "SmtpConfig":
        return cls(
            host=settings.smtp_host.strip(),
            port=settings.smtp_port,
            user=settings.smtp_user.strip(),
            password=settings.smtp_password.get_secret_value(),
            tls=settings.smtp_tls,
        )


TransportFactory = Callable[[SmtpConfig], MailTransport]


class SmtplibTransport:
    """标准库实现：ssl 直连、starttls 升级或明文（none）；有用户名时登录。"""

    def __init__(self, config: SmtpConfig) -> None:
        self._config = config

    def send(self, message: EmailMessage) -> None:
        with self._connect() as client:
            self._login(client)
            client.send_message(message)

    def check(self) -> None:
        with self._connect() as client:
            self._login(client)
            client.noop()

    def _login(self, client: smtplib.SMTP) -> None:
        if not self._config.user:
            return
        try:
            client.login(self._config.user, self._config.password)
        except smtplib.SMTPNotSupportedError as error:
            raise AuthNotSupportedError() from error

    def _connect(self) -> smtplib.SMTP:
        config = self._config
        context = ssl.create_default_context()
        if config.tls == SMTP_TLS_SSL:
            return smtplib.SMTP_SSL(
                config.host, config.port, timeout=config.timeout, context=context
            )
        client = smtplib.SMTP(config.host, config.port, timeout=config.timeout)
        try:
            client.ehlo()
            if config.tls == SMTP_TLS_STARTTLS:
                try:
                    client.starttls(context=context)
                except smtplib.SMTPNotSupportedError as error:
                    raise StartTLSNotSupportedError() from error
                client.ehlo()
        except Exception:
            client.close()
            raise
        return client
