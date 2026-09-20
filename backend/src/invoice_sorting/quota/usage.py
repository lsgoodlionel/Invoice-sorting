"""用量口径：成员数、当月新增记录数、字节换算。

时间一律按 **Asia/Shanghai** 的自然月；业务库里的 datetime 以本地墙钟存储（SQLite 不带时区），
因此月界比较前要去掉时区信息，避免跨月边界时多算或少算一天。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from invoice_sorting.control.members import list_members
from invoice_sorting.db.models import TZ, Expense

MB = 1024 * 1024
DAYS_PAST_MONTH_END = 32


def megabytes(byte_count: int) -> int:
    """向下取整的 MB：与额度按 MB 比较时口径一致（不足 1 MB 记 0）。"""
    return max(0, int(byte_count)) // MB


def month_window(moment: datetime) -> tuple[datetime, datetime]:
    """所在自然月的 [起, 止) 区间（Asia/Shanghai 墙钟、不带时区）。"""
    local = moment.astimezone(TZ) if moment.tzinfo is not None else moment
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    end = (start + timedelta(days=DAYS_PAST_MONTH_END)).replace(day=1)
    return start, end


def count_expenses_created(session: Session, moment: datetime) -> int:
    """当月新增的记录数。

    含已删除记录：删除是软删除，若不计入就能靠“新建再删除”绕过额度。
    """
    start, end = month_window(moment)
    query = (
        select(func.count())
        .select_from(Expense)
        .where(Expense.created_at >= start, Expense.created_at < end)
    )
    return int(session.scalar(query) or 0)


def count_active_members(control: Session, tenant_id: int) -> int:
    """该账套内可用的成员数（账号停用或成员关系停用都不计）。"""
    return sum(1 for member in list_members(control, tenant_id) if member.is_active)


@dataclass(frozen=True)
class QuotaUsage:
    """某账套当前的三项用量；storage 的测量时间与新鲜度一并给出，便于界面说明。"""

    users: int = 0
    storage_bytes: int = 0
    expenses_this_month: int = 0
    storage_measured_at: datetime | None = None
    storage_is_stale: bool = False

    @property
    def storage_mb(self) -> int:
        return megabytes(self.storage_bytes)
