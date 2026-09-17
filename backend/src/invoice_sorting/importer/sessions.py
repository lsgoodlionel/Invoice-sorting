"""导入会话：内存保存本次导入的附件 id，2 小时过期，最多保留 50 个。"""

import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

SESSION_TTL_SECONDS = 2 * 60 * 60
MAX_SESSIONS = 50
_STORE_LOCK = threading.Lock()


@dataclass
class _Entry:
    created_at: float
    attachment_ids: frozenset[int] = field(default_factory=frozenset)


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

    def create(self, attachment_ids: Iterable[int]) -> str:
        session_id = uuid.uuid4().hex
        entry = _Entry(created_at=self._clock(), attachment_ids=frozenset(attachment_ids))
        with self._lock:
            self._entries[session_id] = entry
            self._purge()
        return session_id

    def get(self, session_id: str) -> frozenset[int] | None:
        with self._lock:
            self._purge()
            entry = self._entries.get(session_id)
            return entry.attachment_ids if entry is not None else None

    def remove_attachments(self, session_id: str, attachment_ids: Iterable[int]) -> None:
        """已确认（含留在待归属）的附件移出会话；会话清空时删除。"""
        removed = frozenset(attachment_ids)
        with self._lock:
            entry = self._entries.get(session_id)
            if entry is None:
                return
            remaining = entry.attachment_ids - removed
            if remaining:
                self._entries[session_id] = _Entry(entry.created_at, remaining)
            else:
                del self._entries[session_id]


def get_session_store(app: Any) -> ImportSessionStore:
    """取（必要时创建）挂在 `app.state.import_sessions` 上的会话存储。"""
    with _STORE_LOCK:
        store = getattr(app.state, "import_sessions", None)
        if store is None:
            store = ImportSessionStore()
            app.state.import_sessions = store
        return store
