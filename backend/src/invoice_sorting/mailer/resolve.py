"""解析当前生效的发信配置：环境变量 → 网页配置（控制库）→ 未配置。

- 环境变量 SMTP_HOST 与 SMTP_FROM 都有时整体以环境变量为准（网页只读）；
- 否则用平台管理员在网页上保存的配置（主机与发件人都填了才算已配置）；
- 站点地址：环境变量生效时取环境变量；网页配置时取网页填写的，未填再退回环境变量。
- 通知接收邮箱（有新申请待审批时提醒谁）同样跟随来源：环境变量生效时取环境变量，否则取网页配置。

网页配置的密码是密文，解不开（密钥丢失或更换）时不抛异常，而是带上 password_error，
由发信与测试接口给出“请重新填写 SMTP 密码”的提示。
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from invoice_sorting.common.secret_box import SecretUnavailableError, decrypt_secret
from invoice_sorting.config import Settings
from invoice_sorting.control.mail_models import MAIL_SETTINGS_ROW_ID, MailSettings
from invoice_sorting.mailer.recipients import notify_recipients
from invoice_sorting.mailer.service import MailConfig
from invoice_sorting.mailer.transport import SmtpConfig

SOURCE_ENV = "env"
SOURCE_WEB = "web"
SOURCE_NONE = "none"

MSG_PASSWORD_UNREADABLE = "SMTP 密码无法解密（服务器密钥已更换或丢失），请重新填写 SMTP 密码"


@dataclass(frozen=True)
class ResolvedMail:
    source: str
    config: MailConfig | None
    base_url: str
    notify_emails: tuple[str, ...] = ()

    @property
    def is_configured(self) -> bool:
        return self.config is not None


@dataclass(frozen=True)
class PasswordState:
    value: str = ""
    error: str = ""

    @property
    def is_readable(self) -> bool:
        return not self.error


def env_config(settings: Settings) -> MailConfig | None:
    if not settings.is_smtp_configured:
        return None
    return MailConfig(smtp=SmtpConfig.from_settings(settings), sender=settings.smtp_from.strip())


def read_password(settings: Settings, row: MailSettings) -> PasswordState:
    if not row.password_encrypted:
        return PasswordState()
    try:
        return PasswordState(value=decrypt_secret(settings, row.password_encrypted))
    except SecretUnavailableError:
        return PasswordState(error=MSG_PASSWORD_UNREADABLE)


def is_row_configured(row: MailSettings | None) -> bool:
    return row is not None and bool(row.host.strip() and row.sender.strip())


def web_config(settings: Settings, row: MailSettings) -> MailConfig:
    password = read_password(settings, row)
    smtp = SmtpConfig(
        host=row.host.strip(),
        port=row.port,
        user=row.username.strip(),
        password=password.value,
        tls=row.tls,
    )
    return MailConfig(smtp=smtp, sender=row.sender.strip(), password_error=password.error)


def mail_row(control: Session) -> MailSettings | None:
    return control.get(MailSettings, MAIL_SETTINGS_ROW_ID)


def resolve_mail(settings: Settings, control: Session) -> ResolvedMail:
    env = env_config(settings)
    if env is not None:
        return ResolvedMail(
            source=SOURCE_ENV,
            config=env,
            base_url=settings.public_base_url,
            notify_emails=notify_recipients(settings.signup_notify_emails),
        )
    row = mail_row(control)
    web_base = (row.public_base_url if row is not None else "") or settings.public_base_url
    web_notify = notify_recipients(row.notify_emails if row is not None else "")
    if row is None or not is_row_configured(row):
        return ResolvedMail(
            source=SOURCE_NONE, config=None, base_url=web_base, notify_emails=web_notify
        )
    return ResolvedMail(
        source=SOURCE_WEB,
        config=web_config(settings, row),
        base_url=web_base,
        notify_emails=web_notify,
    )
