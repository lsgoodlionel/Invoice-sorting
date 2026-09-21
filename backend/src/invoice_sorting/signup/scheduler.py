"""每日隐私清理的守护线程（写法同 licensing/scheduler.py，不引入调度框架）。

启动时立刻先执行一次（在线程里，不阻塞应用启动）；任何异常都只记日志，不中断循环。
"""

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)

DAY_SECONDS = 24 * 60 * 60.0
MIN_INTERVAL_SECONDS = 60.0
STOP_TIMEOUT_SECONDS = 5.0
THREAD_NAME = "signup-purge"


class DailyTask:
    """按间隔重复执行一个无参任务。"""

    def __init__(self, task: Callable[[], object], interval: float = DAY_SECONDS) -> None:
        self._task = task
        self._interval = max(MIN_INTERVAL_SECONDS, interval)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name=THREAD_NAME, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=STOP_TIMEOUT_SECONDS)
        self._thread = None

    def run_once(self) -> None:
        try:
            self._task()
        except Exception:  # noqa: BLE001 - 定时任务必须自愈，失败等下一轮
            logger.exception("注册申请隐私清理失败")

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.run_once()
            self._stop.wait(self._interval)
