"""后台定时校验：独立守护线程，按间隔执行一次在线校验。

启动时立刻先查一次（在线程里，不阻塞应用启动）；任何异常都只记日志，
不会让应用起不来，也不会中断循环。
"""

import logging
import threading
from datetime import timedelta

logger = logging.getLogger(__name__)

MIN_INTERVAL_SECONDS = 60.0
SECONDS_PER_HOUR = 3600
STOP_TIMEOUT_SECONDS = 5.0
THREAD_NAME = "license-check"


def interval_seconds(hours: int) -> float:
    """把配置的小时数换算成秒，并设下限避免配置成 0 时空转。"""
    return max(MIN_INTERVAL_SECONDS, timedelta(hours=max(0, hours)).total_seconds())


class LicenseScheduler:
    """周期性调用 LicenseService.run_check()。"""

    def __init__(self, service, interval: float) -> None:
        self._service = service
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
        logger.info("授权定时校验已启动，间隔 %.0f 秒", self._interval)

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=STOP_TIMEOUT_SECONDS)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._run_once()
            self._stop.wait(self._interval)

    def _run_once(self) -> None:
        try:
            self._service.run_check()
        except Exception:  # noqa: BLE001 - 定时任务必须自愈，失败等下一轮
            logger.exception("定时授权校验失败")
