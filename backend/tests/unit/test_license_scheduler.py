"""后台定时校验线程：立即执行一次、可停止、异常不中断循环。"""

import threading

from invoice_sorting.licensing.scheduler import (
    MIN_INTERVAL_SECONDS,
    LicenseScheduler,
    interval_seconds,
)


class CountingService:
    def __init__(self, error: Exception | None = None) -> None:
        self.calls = 0
        self.error = error
        self.done = threading.Event()

    def run_check(self):
        self.calls += 1
        self.done.set()
        if self.error is not None:
            raise self.error


def test_interval_is_converted_from_hours():
    assert interval_seconds(24) == 24 * 3600
    assert interval_seconds(0) == MIN_INTERVAL_SECONDS
    assert interval_seconds(-5) == MIN_INTERVAL_SECONDS


def test_scheduler_checks_immediately_and_stops():
    service = CountingService()
    scheduler = LicenseScheduler(service, interval=3600)

    scheduler.start()
    assert service.done.wait(timeout=5) is True
    scheduler.stop()

    assert service.calls == 1
    assert scheduler.is_running is False


def test_failing_check_does_not_kill_the_thread():
    service = CountingService(error=RuntimeError("网络异常"))
    scheduler = LicenseScheduler(service, interval=3600)

    scheduler.start()
    service.done.wait(timeout=5)

    assert scheduler.is_running is True
    scheduler.stop()


def test_starting_twice_keeps_one_thread():
    service = CountingService()
    scheduler = LicenseScheduler(service, interval=3600)

    scheduler.start()
    service.done.wait(timeout=5)
    scheduler.start()
    scheduler.stop()

    assert service.calls == 1
