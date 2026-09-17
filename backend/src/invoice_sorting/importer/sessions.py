"""导入会话：内存保存本次导入的附件 id 与累计结果，2 小时过期，最多保留 50 个。

分文件导入时逐个文件记入结果（附件 id、重复、错误、提醒、发票提示与建议日期），
finish 时据此从数据库重建凭证项并分组；confirm 依赖 get / remove_attachments。
"""

import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from types import MappingProxyType
from typing import Any

SESSION_TTL_SECONDS = 2 * 60 * 60
MAX_SESSIONS = 50
_STORE_LOCK = threading.Lock()

Record = Mapping[str, Any]


@dataclass(frozen=True)
class SessionSnapshot:
    """会话内容的不可变快照。"""

    attachment_ids: frozenset[int] = frozenset()
    duplicates: tuple[Record, ...] = ()
    errors: tuple[Record, ...] = ()
    notices: tuple[Record, ...] = ()
    warnings: Mapping[int, tuple[str, ...]] = field(default_factory=dict)  # 附件 id → 发票提示
    occurred_on: Mapping[int, date] = field(default_factory=dict)  # 附件 id → 发票建议支出日期


@dataclass(frozen=True)
class _Entry:
    created_at: float
    data: SessionSnapshot = field(default_factory=SessionSnapshot)


def _append(records: tuple[Record, ...], record: Record | None) -> tuple[Record, ...]:
    return records if record is None else (*records, dict(record))


def _with_file(
    data: SessionSnapshot,
    attachment_id: int | None,
    warnings: Sequence[str],
    occurred_on: date | None,
) -> SessionSnapshot:
    if attachment_id is None:
        return data
    dates = dict(data.occurred_on)
    if occurred_on is not None:
        dates[attachment_id] = occurred_on
    return replace(
        data,
        attachment_ids=data.attachment_ids | {attachment_id},
        warnings=MappingProxyType({**data.warnings, attachment_id: tuple(warnings)}),
        occurred_on=MappingProxyType(dates),
    )


class ImportSessionStore:
    """线程安全的导入会话存储；读取时顺带清理过期会话。"""

    def __init__(
        self,
        ttl_seconds: float = SESSION_TTL_SECONDS,
        max_sessions: int = MAX_SESSIONS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max = max_sessions
        self._clock = clock
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._lock = threading.Lock()

    def _purge(self) -> None:
        deadline = self._clock() - self._ttl
        for key in [key for key, entry in self._entries.items() if entry.created_at < deadline]:
            del self._entries[key]
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)

    def _live(self, session_id: str) -> _Entry | None:
        self._purge()
        return self._entries.get(session_id)

    def create(self, attachment_ids: Iterable[int]) -> str:
        """一次性导入：只记录附件 id。"""
        session_id = uuid.uuid4().hex
        data = SessionSnapshot(attachment_ids=frozenset(attachment_ids))
        with self._lock:
            self._entries[session_id] = _Entry(created_at=self._clock(), data=data)
            self._purge()
        return session_id

    def start(self) -> str:
        """分文件导入：创建空会话。"""
        return self.create(())

    def get(self, session_id: str) -> frozenset[int] | None:
        snapshot = self.snapshot(session_id)
        return snapshot.attachment_ids if snapshot is not None else None

    def snapshot(self, session_id: str) -> SessionSnapshot | None:
        with self._lock:
            entry = self._live(session_id)
            return entry.data if entry is not None else None

    def add_file_outcome(
        self,
        session_id: str,
        *,
        attachment_id: int | None = None,
        warnings: Sequence[str] = (),
        occurred_on: date | None = None,
        duplicate: Record | None = None,
        error: Record | None = None,
        notice: Record | None = None,
    ) -> bool:
        """记入单个文件的导入结果；会话不存在（或已过期）时返回 False。"""
        with self._lock:
            entry = self._live(session_id)
            if entry is None:
                return False
            data = _with_file(entry.data, attachment_id, warnings, occurred_on)
            data = replace(
                data,
                duplicates=_append(data.duplicates, duplicate),
                errors=_append(data.errors, error),
                notices=_append(data.notices, notice),
            )
            self._entries[session_id] = replace(entry, data=data)
            return True

    def remove_attachments(self, session_id: str, attachment_ids: Iterable[int]) -> None:
        """已确认（含留在待归属）的附件移出会话；会话内不再有附件时删除。"""
        removed = frozenset(attachment_ids)
        with self._lock:
            entry = self._entries.get(session_id)
            if entry is None:
                return
            remaining = entry.data.attachment_ids - removed
            if not remaining:
                del self._entries[session_id]
                return
            data = replace(
                entry.data,
                attachment_ids=remaining,
                warnings=MappingProxyType(
                    {key: value for key, value in entry.data.warnings.items() if key in remaining}
                ),
                occurred_on=MappingProxyType(
                    {
                        key: value
                        for key, value in entry.data.occurred_on.items()
                        if key in remaining
                    }
                ),
            )
            self._entries[session_id] = replace(entry, data=data)


def get_session_store(app: Any) -> ImportSessionStore:
    """取（必要时创建）挂在 `app.state.import_sessions` 上的会话存储。"""
    with _STORE_LOCK:
        store = getattr(app.state, "import_sessions", None)
        if store is None:
            store = ImportSessionStore()
            app.state.import_sessions = store
        return store
