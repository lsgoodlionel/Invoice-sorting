"""用量日快照：控制库 `usage_snapshot` 每个账套每天一行，运营后台据此看趋势。

不引入调度框架：每次**完整**算出用量后（GET /api/quota、运营后台看用量）顺手更新当天这一行，
并用节流器限制写入频率（同一账套默认 5 分钟最多写一次，跨天立即写）。
写守卫里只按需测量单项，测到的还是“写入前”的值，因此不在那里落快照，
也避免给每个写请求多加一次控制库写入。
"""

import logging
import threading
import time
from collections.abc import Callable, Mapping
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.control.models import UsageSnapshot
from invoice_sorting.quota.constants import KIND_EXPENSES, KIND_STORAGE, KIND_USERS

logger = logging.getLogger(__name__)

MIN_INTERVAL_SECONDS = 300.0
SNAPSHOT_FIELDS = {
    KIND_USERS: "users",
    KIND_STORAGE: "storage_bytes",
    KIND_EXPENSES: "expenses_created",
}


def upsert_snapshot(
    control: Session, tenant_id: int, day: date, values: Mapping[str, int]
) -> UsageSnapshot:
    """写入（或更新）当天的快照；只覆盖本次真正测量过的字段。"""
    row = control.scalar(
        select(UsageSnapshot).where(UsageSnapshot.tenant_id == tenant_id, UsageSnapshot.day == day)
    )
    if row is None:
        row = UsageSnapshot(tenant_id=tenant_id, day=day)
        control.add(row)
    for kind, value in values.items():
        column = SNAPSHOT_FIELDS.get(kind)
        if column is not None:
            setattr(row, column, int(value))
    control.commit()
    return row


class SnapshotThrottle:
    """限制快照写入频率：同一账套在同一天内至多每 N 秒写一次。"""

    def __init__(
        self,
        min_interval: float = MIN_INTERVAL_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._min_interval = max(0.0, min_interval)
        self._monotonic = monotonic
        self._last: dict[str, tuple[date, float]] = {}
        self._lock = threading.RLock()

    def should_write(self, slug: str, day: date) -> bool:
        current = self._monotonic()
        with self._lock:
            previous = self._last.get(slug)
            if previous is not None and previous[0] == day:
                if current - previous[1] < self._min_interval:
                    return False
            self._last = {**self._last, slug: (day, current)}
        return True

    def forget(self) -> None:
        """清空节流记录（测试与手动触发用）。"""
        with self._lock:
            self._last = {}
