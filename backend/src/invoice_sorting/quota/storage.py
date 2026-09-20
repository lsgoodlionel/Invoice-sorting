"""存储用量：文件库目录的字节数，带缓存。

为什么要缓存：文件库可能有几万个文件，遍历一次可能要几秒，绝不能让每个写请求都去扫盘。

缓存策略（按账套分别缓存）：
- **命中**：距上次测量不到 TTL（默认 5 分钟）直接返回，不碰磁盘；
- **首次**：没有任何旧值时同步扫一次（必须给出数字才能判额度）；
- **过期**：先把旧值返回给本次请求（标记 is_stale），同时丢到后台线程刷新，
  因此“目录很大”只会让数字晚几秒变化，不会让请求变慢；
- **失败**：保留旧值并把测量时间推到现在，避免磁盘异常时每个请求都重试一次。

因此存储额度的判定最多滞后一个 TTL：宁可让超限稍晚生效，也不让每次上传都等扫盘。
"""

import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from invoice_sorting.db.models import now

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 300.0
THREAD_NAME = "quota-storage"


def _entry_size(entry: os.DirEntry) -> int:
    try:
        return entry.stat(follow_symlinks=False).st_size
    except OSError:  # 扫描过程中文件被删除或无权限，按 0 计
        return 0


def directory_size(path: Path) -> int:
    """目录内所有文件的字节数之和；目录不存在按 0。不跟随符号链接。"""
    total = 0
    pending = [Path(path)]
    while pending:
        current = pending.pop()
        try:
            entries = list(os.scandir(current))
        except (FileNotFoundError, NotADirectoryError, PermissionError):
            continue
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                pending.append(Path(entry.path))
            elif entry.is_file(follow_symlinks=False):
                total += _entry_size(entry)
    return total


@dataclass(frozen=True)
class StorageReading:
    """一次测量结果；is_stale 表示这是过期旧值，后台正在刷新。"""

    bytes_used: int
    measured_at: datetime
    is_stale: bool = False


def _spawn(job: Callable[[], None]) -> None:
    threading.Thread(target=job, name=THREAD_NAME, daemon=True).start()


class StorageCache:
    """按账套缓存文件库大小。线程安全：字典读写在锁内，扫盘在锁外。"""

    def __init__(
        self,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        scanner: Callable[[Path], int] = directory_size,
        clock: Callable[[], datetime] = now,
        runner: Callable[[Callable[[], None]], None] = _spawn,
    ) -> None:
        self._ttl = max(0.0, ttl_seconds)
        self._scanner = scanner
        self._clock = clock
        self._runner = runner
        self._entries: dict[str, StorageReading] = {}
        self._refreshing: set[str] = set()
        self._lock = threading.RLock()

    def get(self, slug: str, directory: Path) -> StorageReading:
        """该账套的存储用量；过期时返回旧值并在后台刷新。"""
        with self._lock:
            entry = self._entries.get(slug)
            if entry is not None and self._is_fresh(entry):
                return entry
            should_refresh = entry is not None and slug not in self._refreshing
            if should_refresh:
                self._refreshing.add(slug)
        if entry is None:
            return self._measure(slug, directory)
        if should_refresh:
            self._runner(lambda: self._refresh(slug, directory))
        return replace(entry, is_stale=True)

    def invalidate(self, slug: str | None = None) -> None:
        """丢弃缓存（某个账套或全部），下次读取重新扫盘。"""
        with self._lock:
            if slug is None:
                self._entries = {}
            else:
                self._entries = {key: value for key, value in self._entries.items() if key != slug}

    def _is_fresh(self, entry: StorageReading) -> bool:
        return (self._clock() - entry.measured_at).total_seconds() < self._ttl

    def _refresh(self, slug: str, directory: Path) -> None:
        try:
            self._measure(slug, directory)
        finally:
            with self._lock:
                self._refreshing.discard(slug)

    def _measure(self, slug: str, directory: Path) -> StorageReading:
        try:
            value = max(0, int(self._scanner(directory)))
        except Exception:  # noqa: BLE001 - 统计失败不能挡住请求，保留旧值并退避一个 TTL
            logger.exception("统计账套 %s 的存储用量失败", slug)
            return self._back_off(slug)
        reading = StorageReading(bytes_used=value, measured_at=self._clock())
        with self._lock:
            self._entries = {**self._entries, slug: reading}
        return reading

    def _back_off(self, slug: str) -> StorageReading:
        with self._lock:
            previous = self._entries.get(slug)
            reading = StorageReading(
                bytes_used=previous.bytes_used if previous else 0, measured_at=self._clock()
            )
            self._entries = {**self._entries, slug: reading}
        return reading
