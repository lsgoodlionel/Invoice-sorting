"""登录失败限制（内存、线程安全）：同一键 15 分钟内失败 5 次，锁定 15 分钟。

次数、窗口与锁定时长可按用途调整（例如注册申请按 IP 每小时 5 次），默认值即登录的规则。
"""

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

MAX_FAILURES = 5
WINDOW_SECONDS = 15 * 60
LOCK_SECONDS = 15 * 60
MAX_TRACKED_KEYS = 10_000


@dataclass(frozen=True)
class _Entry:
    failures: tuple[float, ...] = ()
    locked_until: float = 0.0


class LoginRateLimiter:
    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        max_tracked: int = MAX_TRACKED_KEYS,
        max_failures: int = MAX_FAILURES,
        window_seconds: float = WINDOW_SECONDS,
        lock_seconds: float = LOCK_SECONDS,
    ) -> None:
        self._clock = clock
        self._max_tracked = max_tracked
        self._max_failures = max(1, max_failures)
        self._window = window_seconds
        self._lock_seconds = lock_seconds
        self._entries: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def retry_after(self, key: str) -> int:
        """仍处于锁定时返回剩余秒数（向上取整），否则 0。"""
        with self._lock:
            entry = self._entries.get(key)
            remaining = entry.locked_until - self._clock() if entry else 0
            return math.ceil(remaining) if remaining > 0 else 0

    def record_failure(self, key: str) -> None:
        with self._lock:
            current = self._clock()
            entry = self._entries.pop(key, _Entry())
            if entry.locked_until > current:
                self._entries[key] = entry
                return
            recent = tuple(t for t in entry.failures if current - t < self._window)
            failures = (*recent, current)
            if len(failures) >= self._max_failures:
                self._entries[key] = _Entry(locked_until=current + self._lock_seconds)
            else:
                self._entries[key] = _Entry(failures=failures)
            self._enforce_capacity(current)

    def reset(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def tracked_count(self) -> int:
        with self._lock:
            return len(self._entries)

    def _enforce_capacity(self, current: float) -> None:
        if len(self._entries) <= self._max_tracked:
            return
        self._entries = {
            k: e for k, e in self._entries.items() if not _is_stale(e, current, self._window)
        }
        while len(self._entries) > self._max_tracked:
            del self._entries[next(iter(self._entries))]


def _is_stale(entry: _Entry, current: float, window: float = WINDOW_SECONDS) -> bool:
    is_locked = entry.locked_until > current
    has_recent = any(current - t < window for t in entry.failures)
    return not is_locked and not has_recent


def minutes_label(seconds: int) -> int:
    return max(1, math.ceil(seconds / 60))
