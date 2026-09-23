"""「有新申请待审批」提醒：申请进入待审批时，给平台配置的通知邮箱发一封。

- **不阻塞提交**：交给 BackgroundTasks，在响应发出之后用一个新的控制库会话发送，
  发信慢、失败甚至异常都不影响 `POST /api/signup/applications` 的返回。
- **失败只留痕**：结果写回申请的 `notify_status` / `notify_error`，并记一条日志。
- **有上限**：同一实例每小时最多 NOTIFY_MAX_PER_WINDOW 封，超出的直接跳过并记为 throttled，
  后台「申请」页签本来就有待审批角标，不需要靠邮件把人淹了。
- 未配置 SMTP 或没填通知邮箱时什么都不做（记为 skipped），不报错。
"""

import logging
from typing import Any

from fastapi import BackgroundTasks, Request
from sqlalchemy.orm import Session

from invoice_sorting.auth.ratelimit import LoginRateLimiter
from invoice_sorting.control.models import Account
from invoice_sorting.control.signup_models import (
    APPLICATION_PENDING,
    NOTIFY_FAILED,
    NOTIFY_SKIPPED,
    NOTIFY_THROTTLED,
    SignupApplication,
)
from invoice_sorting.mailer.resolve import resolve_mail
from invoice_sorting.mailer.service import STATE_MAILER_KEY, MailerFactory
from invoice_sorting.signup.alerts import pending_alert

logger = logging.getLogger(__name__)

STATE_NOTIFY_LIMITER = "signup_notify_limiter"
NOTIFY_MAX_PER_WINDOW = 20
NOTIFY_WINDOW_SECONDS = 60 * 60
LIMIT_KEY = "instance"
RECIPIENT_SEPARATOR = ", "
MSG_THROTTLED = f"每小时最多发送 {NOTIFY_MAX_PER_WINDOW} 封提醒，本条已跳过"


def install_notify_limiter(app: Any) -> None:
    """整个实例共用一个计数器（限的是发信总量，与申请人来源无关）。"""
    setattr(
        app.state,
        STATE_NOTIFY_LIMITER,
        LoginRateLimiter(
            max_failures=NOTIFY_MAX_PER_WINDOW,
            window_seconds=NOTIFY_WINDOW_SECONDS,
            lock_seconds=NOTIFY_WINDOW_SECONDS,
        ),
    )


def schedule_pending_alert(
    request: Request, background: BackgroundTasks, control: Session, application_id: int
) -> None:
    """先提交这条申请（后台任务要用新会话读它、并把发送结果写回去），再把提醒排到响应之后。"""
    control.commit()
    background.add_task(send_pending_alert, request.app, application_id)


def send_pending_alert(app: Any, application_id: int) -> str:
    """后台任务入口：任何异常都只记录，绝不向上冒泡。"""
    try:
        return _notify(app, application_id)
    except Exception:  # noqa: BLE001 - 提醒发不出去不能影响任何业务流程
        logger.exception("发送待审批提醒时出错（申请 %s）", application_id)
        return NOTIFY_FAILED


def _notify(app: Any, application_id: int) -> str:
    with app.state.control_session_factory() as control:
        application = control.get(SignupApplication, application_id)
        if application is None or application.status != APPLICATION_PENDING:
            return NOTIFY_SKIPPED
        status, error = _deliver(app, control, application)
        application.notify_status = status
        application.notify_error = error
        control.commit()
        return status


def _mailer_factory(app: Any) -> MailerFactory:
    return getattr(app.state, STATE_MAILER_KEY)


def _referrer(control: Session, application: SignupApplication) -> Account | None:
    account_id = application.referrer_account_id
    return control.get(Account, account_id) if account_id is not None else None


def _is_within_limit(app: Any) -> bool:
    limiter: LoginRateLimiter = getattr(app.state, STATE_NOTIFY_LIMITER)
    if limiter.retry_after(LIMIT_KEY):
        return False
    limiter.record_failure(LIMIT_KEY)
    return True


def _deliver(app: Any, control: Session, application: SignupApplication) -> tuple[str, str]:
    resolved = resolve_mail(app.state.settings, control)
    if resolved.config is None or not resolved.notify_emails:
        return NOTIFY_SKIPPED, ""
    if not _is_within_limit(app):
        logger.warning("待审批提醒超过每小时上限，申请 %s 未发送", application.id)
        return NOTIFY_THROTTLED, MSG_THROTTLED
    notice = pending_alert(application, _referrer(control, application), resolved.base_url)
    to = RECIPIENT_SEPARATOR.join(resolved.notify_emails)
    result = _mailer_factory(app).build(resolved.config).send(to, notice.subject, notice.body)
    if not result.is_sent:
        logger.warning("待审批提醒发送失败（申请 %s）：%s", application.id, result.error)
    return result.status, result.error
