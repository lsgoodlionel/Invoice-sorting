"""装配入口：发信服务、限流器、路由与每日隐私清理，供 main.create_app 调用。"""

from typing import Any

from invoice_sorting.config import Settings
from invoice_sorting.mailer.service import Mailer
from invoice_sorting.signup.deps import install_signup_state
from invoice_sorting.signup.platform_router import router as platform_router
from invoice_sorting.signup.public_router import router as public_router
from invoice_sorting.signup.purge import run_purge
from invoice_sorting.signup.referral_router import router as referral_router
from invoice_sorting.signup.scheduler import DailyTask

ROUTERS = (public_router, referral_router, platform_router)


def install_signup(app: Any, settings: Settings) -> None:
    install_signup_state(app, Mailer(settings))


def start_purge_task(app: Any, settings: Settings) -> DailyTask | None:
    """多账套部署才有注册申请，才需要清理；单账套不启动线程。"""
    if not settings.is_saas:
        return None
    task = DailyTask(lambda: run_purge(app.state.control_session_factory))
    task.start()
    return task
