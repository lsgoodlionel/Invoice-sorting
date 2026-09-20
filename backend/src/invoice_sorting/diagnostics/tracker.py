"""故障计数的持久化（设计《日志与故障上报》5.4 限流）。

状态落在 `data_dir/日志/.故障限流.json`：崩溃重启循环下每次进程都是新的，
计数只放内存会让限流形同虚设。读写都不抛异常，最坏情况退化为“这次不限流”。
"""

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path

from invoice_sorting.diagnostics.throttle import (
    ThrottleDecision,
    ThrottleState,
    load_state,
    record_fault,
    serialize_state,
)

logger = logging.getLogger(__name__)

STATE_FILENAME = ".故障限流.json"


class FaultTracker:
    """带锁的限流状态；每次更新整体替换 state 并落盘。"""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._state = _read(path)

    @property
    def path(self) -> Path:
        return self._path

    def snapshot(self) -> ThrottleState:
        with self._lock:
            return self._state

    def record(self, fingerprint: str, moment: datetime) -> ThrottleDecision:
        """记录一次故障；返回是否应当生成诊断包。"""
        with self._lock:
            decision = record_fault(self._state, fingerprint, moment)
            self._state = decision.state
            _write(self._path, decision.state)
            return decision


def state_path(logs_dir: Path) -> Path:
    return logs_dir / STATE_FILENAME


def _read(path: Path) -> ThrottleState:
    try:
        return load_state(json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return ThrottleState()
    except (OSError, ValueError):
        logger.info("故障限流状态读取失败，按空状态处理：%s", path.name)
        return ThrottleState()


def _write(path: Path, state: ThrottleState) -> None:
    """先写临时文件再替换，避免断电留下半截 JSON。"""
    temporary = path.with_suffix(".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(serialize_state(state), ensure_ascii=False), encoding="utf-8"
        )
        os.replace(temporary, path)
    except (OSError, TypeError, ValueError):
        logger.info("故障限流状态写入失败，本次只在内存中生效")
