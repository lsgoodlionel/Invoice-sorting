"""审批：批准（发放注册码并通知）、否决（通知原因）、重新发送。

通知失败不影响审批结果：只记录发送状态与脱敏后的原因。未配置 SMTP 时不发信，
把注册链接与可复制的通知文字返回给管理员自行转告。注册码只存哈希，因此
「重新发送」批准通知会**换发新码**（旧链接随即失效、有效期重新计算）。
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from invoice_sorting.common.errors import AppError, ConflictError
from invoice_sorting.control.signup_models import (
    APPLICATION_APPROVED,
    APPLICATION_PENDING,
    APPLICATION_REJECTED,
    MAIL_SENT,
    SignupApplication,
)
from invoice_sorting.db.models import now
from invoice_sorting.mailer.service import Mailer
from invoice_sorting.signup.codes import hash_code, new_register_code
from invoice_sorting.signup.constants import (
    MSG_NOT_PENDING,
    MSG_RESEND_NOT_ALLOWED,
    MSG_RESEND_PURGED,
)
from invoice_sorting.signup.notices import (
    Notice,
    approved_notice,
    register_link,
    rejected_notice,
)
from invoice_sorting.signup.provision import TenantOptions, apply_plan, plan_tenant
from invoice_sorting.signup.settings_store import load_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Delivery:
    """一次通知的结果；没发出去（未配置或失败）时附上链接与文字供管理员转告。"""

    status: str
    error: str = ""
    link: str = ""
    text: str = ""


@dataclass(frozen=True)
class ReviewResult:
    application: SignupApplication
    delivery: Delivery


@dataclass(frozen=True)
class Notifier:
    """发信所需的上下文：发信服务与生成链接用的站点地址。"""

    mailer: Mailer
    base_url: str = ""


def deliver(application: SignupApplication, notice: Notice, notifier: Notifier) -> Delivery:
    result = notifier.mailer.send(application.email, notice.subject, notice.body)
    application.mail_status = result.status
    application.mail_error = result.error
    application.mail_sent_at = now() if result.is_sent else application.mail_sent_at
    if result.status == MAIL_SENT:
        return Delivery(status=result.status)
    return Delivery(status=result.status, error=result.error, link=notice.link, text=notice.body)


def _issue_code(control: Session, application: SignupApplication) -> tuple[str, datetime]:
    days = load_settings(control).code_valid_days
    code = new_register_code()
    expires_at = now() + timedelta(days=days)
    application.code_hash = hash_code(code)
    application.code_expires_at = expires_at
    return code, expires_at


def send_code(control: Session, application: SignupApplication, notifier: Notifier) -> Delivery:
    """（换）发注册码并通知申请人。"""
    code, expires_at = _issue_code(control, application)
    link = register_link(notifier.base_url, code)
    delivery = deliver(application, approved_notice(application.name, link, expires_at), notifier)
    control.flush()
    return delivery


def _require_pending(application: SignupApplication) -> None:
    if application.status != APPLICATION_PENDING:
        raise ConflictError(MSG_NOT_PENDING)


def mark_approved(
    control: Session,
    application: SignupApplication,
    options: TenantOptions,
    reviewer_id: int | None,
) -> None:
    apply_plan(application, plan_tenant(control, application, options))
    application.status = APPLICATION_APPROVED
    application.reviewer_account_id = reviewer_id
    application.reviewed_at = now()


def approve(
    control: Session,
    application: SignupApplication,
    options: TenantOptions,
    reviewer_id: int | None,
    notifier: Notifier,
) -> ReviewResult:
    _require_pending(application)
    mark_approved(control, application, options, reviewer_id)
    delivery = send_code(control, application, notifier)
    logger.info("注册申请 %s 已批准，操作人 %s", application.id, reviewer_id)
    return ReviewResult(application=application, delivery=delivery)


def reject(
    control: Session,
    application: SignupApplication,
    reason: str,
    reviewer_id: int | None,
    notifier: Notifier,
) -> ReviewResult:
    _require_pending(application)
    application.status = APPLICATION_REJECTED
    application.reject_reason = reason
    application.reviewer_account_id = reviewer_id
    application.reviewed_at = now()
    delivery = deliver(application, rejected_notice(application.name, reason), notifier)
    control.flush()
    logger.info("注册申请 %s 已否决，操作人 %s", application.id, reviewer_id)
    return ReviewResult(application=application, delivery=delivery)


def resend(
    control: Session,
    application: SignupApplication,
    notifier: Notifier,
    operator_id: int | None = None,
) -> ReviewResult:
    """已批准待注册：换发新码并重发；已否决：重发否决通知。其余状态 409。"""
    if application.is_purged:
        raise AppError(MSG_RESEND_PURGED, status_code=409)
    if application.status == APPLICATION_APPROVED:
        delivery = send_code(control, application, notifier)
    elif application.status == APPLICATION_REJECTED:
        notice = rejected_notice(application.name, application.reject_reason)
        delivery = deliver(application, notice, notifier)
        control.flush()
    else:
        raise ConflictError(MSG_RESEND_NOT_ALLOWED)
    logger.info(
        "注册申请 %s 已重新发送通知（%s），操作人 %s", application.id, delivery.status, operator_id
    )
    return ReviewResult(application=application, delivery=delivery)
