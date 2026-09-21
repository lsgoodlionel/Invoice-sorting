"""隐私清理：否决满 180 天的申请清除个人资料，只保留状态与时间（统计计数不变）。

由后台守护线程每天执行一次（见 signup/scheduler.py），启动时也会先跑一次。
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from invoice_sorting.control.signup_models import APPLICATION_REJECTED, SignupApplication
from invoice_sorting.db.models import now
from invoice_sorting.signup.constants import PURGE_AFTER_DAYS

logger = logging.getLogger(__name__)

PERSONAL_FIELDS = ("name", "email", "identity", "needs", "ledger_name", "ip_hash", "reject_reason")


def purge_cutoff(moment: datetime | None = None) -> datetime:
    return (moment or now()) - timedelta(days=PURGE_AFTER_DAYS)


def purge_rejected(control: Session, moment: datetime | None = None) -> int:
    """清除到期的否决申请的个人资料，返回本次清除的条数。调用方负责提交。"""
    query = select(SignupApplication).where(
        SignupApplication.status == APPLICATION_REJECTED,
        SignupApplication.is_purged.is_(False),
        SignupApplication.reviewed_at < purge_cutoff(moment),
    )
    rows = list(control.scalars(query))
    stamp = now()
    for row in rows:
        for field in PERSONAL_FIELDS:
            setattr(row, field, "")
        row.is_purged = True
        row.purged_at = stamp
    control.flush()
    return len(rows)


def run_purge(factory: sessionmaker[Session]) -> int:
    with factory() as control:
        count = purge_rejected(control)
        control.commit()
    if count:
        logger.info("已清除 %s 条否决满 %s 天的注册申请个人资料", count, PURGE_AFTER_DAYS)
    return count
