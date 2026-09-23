"""通知接收邮箱（英文逗号分隔的多个地址）的解析与上限。

网页填写的值在接口边界已校验；环境变量来源没有校验入口，因此读取时再过滤一次：
丢掉格式不对的地址并记一条日志，不让一个写错的地址连累其余收件人。
"""

import logging

from invoice_sorting.signup.codes import is_valid_email

logger = logging.getLogger(__name__)

NOTIFY_EMAILS_MAX = 5
SEPARATOR = ","


def split_notify_emails(text: str) -> tuple[str, ...]:
    """按逗号拆分、去首尾空白、丢掉空项；不校验格式也不限制数量。"""
    return tuple(part.strip() for part in (text or "").split(SEPARATOR) if part.strip())


def join_notify_emails(emails: tuple[str, ...]) -> str:
    return SEPARATOR.join(emails)


def notify_recipients(text: str) -> tuple[str, ...]:
    """实际发信用的收件人：只保留格式正确的地址，最多前 NOTIFY_EMAILS_MAX 个。"""
    items = split_notify_emails(text)
    valid = tuple(item for item in items if is_valid_email(item))
    if len(valid) != len(items):
        logger.warning("通知接收邮箱中有 %s 个地址格式不正确，已跳过", len(items) - len(valid))
    return valid[:NOTIFY_EMAILS_MAX]
