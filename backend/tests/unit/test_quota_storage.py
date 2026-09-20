"""存储用量缓存：命中不重扫盘，过期先返回旧值再后台刷新，目录不存在按 0 处理。"""

from datetime import timedelta

from invoice_sorting.db.models import now
from invoice_sorting.quota.storage import StorageCache, directory_size


class FakeClock:
    """可手动推进的时钟，避免依赖真实时间。"""

    def __init__(self) -> None:
        self.moment = now()

    def __call__(self):
        return self.moment

    def advance(self, seconds: float) -> None:
        self.moment = self.moment + timedelta(seconds=seconds)


def run_now(job) -> None:
    """同步执行“后台刷新”，让测试结果确定。"""
    job()


def write_file(directory, name: str, size: int) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_bytes(b"x" * size)


def test_directory_size_sums_files_recursively(tmp_path):
    write_file(tmp_path / "库", "a.pdf", 100)
    write_file(tmp_path / "库" / "2026" / "09", "b.pdf", 50)

    assert directory_size(tmp_path / "库") == 150


def test_directory_size_of_missing_directory_is_zero(tmp_path):
    assert directory_size(tmp_path / "不存在") == 0


def test_second_read_within_ttl_hits_the_cache(tmp_path):
    scans: list = []
    cache = StorageCache(ttl_seconds=60, scanner=lambda path: scans.append(path) or 10)

    first = cache.get("alpha", tmp_path)
    second = cache.get("alpha", tmp_path)

    assert (first.bytes_used, second.bytes_used) == (10, 10)
    assert len(scans) == 1
    assert second.is_stale is False


def test_expired_entry_returns_the_old_value_and_refreshes_in_background(tmp_path):
    sizes = iter([10, 999])
    clock = FakeClock()
    cache = StorageCache(
        ttl_seconds=60, scanner=lambda path: next(sizes), clock=clock, runner=run_now
    )
    cache.get("alpha", tmp_path)

    clock.advance(61)
    stale = cache.get("alpha", tmp_path)

    assert (stale.bytes_used, stale.is_stale) == (10, True)  # 本次请求不等待磁盘
    assert cache.get("alpha", tmp_path).bytes_used == 999  # 刷新后的值


def test_each_tenant_is_cached_separately(tmp_path):
    cache = StorageCache(ttl_seconds=60, scanner=lambda path: len(str(path)))

    alpha = cache.get("alpha", tmp_path / "alpha")
    beta = cache.get("beta", tmp_path / "beta-long")

    assert alpha.bytes_used != beta.bytes_used


def test_invalidate_forces_a_fresh_scan(tmp_path):
    sizes = iter([10, 20])
    cache = StorageCache(ttl_seconds=60, scanner=lambda path: next(sizes))
    cache.get("alpha", tmp_path)

    cache.invalidate("alpha")

    assert cache.get("alpha", tmp_path).bytes_used == 20


def test_failed_refresh_keeps_the_previous_value(tmp_path):
    calls = {"n": 0}

    def flaky(path) -> int:
        calls["n"] += 1
        if calls["n"] > 1:
            raise OSError("磁盘不可读")
        return 10

    clock = FakeClock()
    cache = StorageCache(ttl_seconds=60, scanner=flaky, clock=clock, runner=run_now)
    cache.get("alpha", tmp_path)
    clock.advance(61)

    assert cache.get("alpha", tmp_path).bytes_used == 10
    assert cache.get("alpha", tmp_path).bytes_used == 10
