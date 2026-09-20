"""写操作守卫：判定哪些请求算写操作，以及多个拒绝原因如何组合。"""

import pytest

from invoice_sorting.common.errors import AppError
from invoice_sorting.licensing.guard import (
    WriteBlock,
    find_write_block,
    is_write_request,
    register_write_guard,
    write_guards,
)


class FakeApp:
    """只提供 state 的应用替身。"""

    def __init__(self) -> None:
        self.state = type("State", (), {})()


class FakeConnection:
    def __init__(self, app, method: str = "POST", path: str = "/api/expenses") -> None:
        self.scope = {"app": app, "method": method, "path": path, "type": "http"}


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("GET", "/api/expenses", False),
        ("HEAD", "/api/expenses", False),
        ("POST", "/api/expenses", True),
        ("PATCH", "/api/expenses/1", True),
        ("DELETE", "/api/expenses/1", True),
        ("PUT", "/api/settings", True),
        ("POST", "/api/auth/login", False),
        ("POST", "/api/auth/logout", False),
        ("POST", "/api/license/recheck", False),
        ("POST", "/api/platform/license/verify", False),
        ("POST", "/api/backup", False),
        ("POST", "/api/batches/3/export", False),
        ("POST", "/login", False),
    ],
)
def test_write_request_detection(method, path, expected):
    assert is_write_request(method, path) is expected


def test_guards_are_evaluated_in_order_and_first_block_wins():
    app = FakeApp()
    register_write_guard(app, lambda conn: None)
    register_write_guard(app, lambda conn: WriteBlock(code="quota", message="额度已用完"))
    register_write_guard(app, lambda conn: WriteBlock(code="late", message="不应到达"))

    block = find_write_block(FakeConnection(app))

    assert block is not None
    assert block.code == "quota"


def test_registering_a_guard_does_not_mutate_the_previous_tuple():
    app = FakeApp()
    register_write_guard(app, lambda conn: None)
    before = write_guards(app)
    register_write_guard(app, lambda conn: WriteBlock(code="x", message="y"))

    assert len(before) == 1
    assert len(write_guards(app)) == 2


def test_no_guards_means_writable():
    app = FakeApp()

    assert find_write_block(FakeConnection(app)) is None


def test_ensure_writable_raises_403_with_chinese_reason():
    from invoice_sorting.licensing.guard import ensure_writable

    app = FakeApp()
    register_write_guard(app, lambda conn: WriteBlock(code="license", message="授权已过期，只读"))

    with pytest.raises(AppError) as excinfo:
        ensure_writable(FakeConnection(app))

    assert excinfo.value.status_code == 403
    assert "只读" in excinfo.value.message
