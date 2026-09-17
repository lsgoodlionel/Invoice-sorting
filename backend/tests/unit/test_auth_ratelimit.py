"""登录失败限制：15 分钟内 5 次失败锁定 15 分钟，可注入时钟。"""

import threading

from invoice_sorting.auth.ratelimit import LoginRateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def make() -> tuple[LoginRateLimiter, FakeClock]:
    clock = FakeClock()
    return LoginRateLimiter(clock=clock), clock


def test_locks_after_five_failures():
    limiter, _ = make()
    for _ in range(4):
        limiter.record_failure("1.2.3.4")
        assert limiter.retry_after("1.2.3.4") == 0
    limiter.record_failure("1.2.3.4")
    assert limiter.retry_after("1.2.3.4") == 15 * 60
    assert limiter.retry_after("5.6.7.8") == 0


def test_lock_expires_after_fifteen_minutes():
    limiter, clock = make()
    for _ in range(5):
        limiter.record_failure("ip")
    clock.advance(14 * 60)
    assert limiter.retry_after("ip") == 60
    clock.advance(60)
    assert limiter.retry_after("ip") == 0
    limiter.record_failure("ip")  # 解锁后重新计数
    assert limiter.retry_after("ip") == 0


def test_failures_outside_window_do_not_count():
    limiter, clock = make()
    for _ in range(4):
        limiter.record_failure("ip")
    clock.advance(15 * 60 + 1)
    limiter.record_failure("ip")
    assert limiter.retry_after("ip") == 0


def test_reset_clears_failures():
    limiter, _ = make()
    for _ in range(4):
        limiter.record_failure("ip")
    limiter.reset("ip")
    limiter.record_failure("ip")
    assert limiter.retry_after("ip") == 0


def test_tracked_keys_are_bounded():
    clock = FakeClock()
    limiter = LoginRateLimiter(clock=clock, max_tracked=3)
    for key in ("a", "b", "c", "d"):
        limiter.record_failure(key)
    assert limiter.tracked_count() == 3


def test_thread_safe_counting():
    limiter = LoginRateLimiter()
    threads = [threading.Thread(target=limiter.record_failure, args=("ip",)) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert limiter.retry_after("ip") > 0


def test_failures_while_locked_do_not_extend_lock():
    limiter, clock = make()
    for _ in range(5):
        limiter.record_failure("ip")
    clock.advance(10 * 60)
    limiter.record_failure("ip")
    assert limiter.retry_after("ip") == 5 * 60
