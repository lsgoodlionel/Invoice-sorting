"""把发信/连接异常翻译成固定的中文分类与说明。

**绝不拼接服务器原始响应**：部分服务器会在错误里回显用户名甚至密码，只按异常类型给文案。
"""

import smtplib
import ssl
from dataclasses import dataclass

CATEGORY_OK = "ok"
CATEGORY_CONNECT = "connect"
CATEGORY_TIMEOUT = "timeout"
CATEGORY_TLS = "tls"
CATEGORY_AUTH = "auth"
CATEGORY_SENDER = "sender"
CATEGORY_RECIPIENT = "recipient"
CATEGORY_PASSWORD = "password"
CATEGORY_OTHER = "other"

MSG_AUTH_FAILED = "邮件服务器登录失败，请检查 SMTP 用户名与密码配置"
MSG_RECIPIENT_REFUSED = "收件地址被邮件服务器拒收"
MSG_SENDER_REFUSED = "发件地址被邮件服务器拒绝，请核对发件人（多数邮箱要求与登录账号一致）"
MSG_TIMEOUT = "连接邮件服务器超时"
MSG_CONNECT_FAILED = "无法连接邮件服务器"
MSG_TLS_FAILED = "TLS 加密握手失败，请核对加密方式与端口（SSL 常用 465，STARTTLS 常用 587）"
MSG_SERVER_REFUSED = "邮件服务器拒绝了本次发送（代码 {code}）"
MSG_UNKNOWN = "邮件发送失败"
MSG_AUTH_NOT_SUPPORTED = (
    "邮件服务器不支持登录（AUTH）：请核对端口与加密方式（多数邮箱需 SSL 465 或 STARTTLS 587），"
    "若这是免登录的内网中继，请清空账号"
)
MSG_STARTTLS_NOT_SUPPORTED = (
    "邮件服务器不支持 STARTTLS：请改用 SSL（常用端口 465），或确认端口是否正确"
)


class AuthNotSupportedError(smtplib.SMTPException):
    """服务器未提供 AUTH 扩展，却配置了账号。"""


class StartTLSNotSupportedError(smtplib.SMTPException):
    """选择了 STARTTLS，但服务器未提供该扩展。"""


@dataclass(frozen=True)
class ErrorInfo:
    category: str
    message: str


def classify_error(error: BaseException) -> ErrorInfo:
    """顺序有讲究：子类在前（认证失败是响应异常的子类，SSL 错误是 OSError 的子类）。"""
    if isinstance(error, AuthNotSupportedError):
        return ErrorInfo(CATEGORY_AUTH, MSG_AUTH_NOT_SUPPORTED)
    if isinstance(error, StartTLSNotSupportedError):
        return ErrorInfo(CATEGORY_TLS, MSG_STARTTLS_NOT_SUPPORTED)
    if isinstance(error, smtplib.SMTPAuthenticationError):
        return ErrorInfo(CATEGORY_AUTH, MSG_AUTH_FAILED)
    if isinstance(error, smtplib.SMTPRecipientsRefused):
        return ErrorInfo(CATEGORY_RECIPIENT, MSG_RECIPIENT_REFUSED)
    if isinstance(error, smtplib.SMTPSenderRefused):
        return ErrorInfo(CATEGORY_SENDER, MSG_SENDER_REFUSED)
    if isinstance(error, (ssl.SSLError, smtplib.SMTPNotSupportedError)):
        return ErrorInfo(CATEGORY_TLS, MSG_TLS_FAILED)
    if isinstance(error, smtplib.SMTPResponseException):
        return ErrorInfo(CATEGORY_OTHER, MSG_SERVER_REFUSED.format(code=error.smtp_code))
    if isinstance(error, TimeoutError):
        return ErrorInfo(CATEGORY_TIMEOUT, MSG_TIMEOUT)
    if isinstance(error, (smtplib.SMTPException, OSError)):
        return ErrorInfo(CATEGORY_CONNECT, MSG_CONNECT_FAILED)
    return ErrorInfo(CATEGORY_OTHER, MSG_UNKNOWN)


def describe_error(error: BaseException) -> str:
    return classify_error(error).message
