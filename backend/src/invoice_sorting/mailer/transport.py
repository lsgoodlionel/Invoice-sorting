"""SMTP 传输层：只负责“把一封信交给邮件服务器”。

业务代码只依赖 `MailTransport` 协议，测试替换成内存实现，**绝不真实发信或联网**。
凭证只在建立连接时使用，不写入任何日志与异常文案。
"""

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from invoice_sorting.config import SMTP_TLS_SSL, Settings

CONNECT_TIMEOUT_SECONDS = 10.0


class MailTransport(Protocol):
    def send(self, message: EmailMessage) -> None: ...


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


class SmtplibTransport:
    """标准库实现：ssl 直连或 starttls 升级；有用户名时登录。"""

    def __init__(self, config: SmtpConfig) -> None:
        self._config = config

    def send(self, message: EmailMessage) -> None:
        with self._connect() as client:
            if self._config.user:
                client.login(self._config.user, self._config.password)
            client.send_message(message)

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
            client.starttls(context=context)
            client.ehlo()
        except Exception:
            client.close()
            raise
        return client
