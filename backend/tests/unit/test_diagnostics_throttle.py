"""故障指纹与限流（设计《日志与故障上报》5 触发方式）。"""

from datetime import datetime, timedelta

from invoice_sorting.diagnostics.fingerprint import fault_from_exception, make_fingerprint
from invoice_sorting.diagnostics.throttle import (
    BURST_THRESHOLD,
    DAILY_TOTAL,
    ThrottleState,
    load_state,
    record_fault,
    serialize_state,
)

START = datetime(2026, 9, 20, 10, 0, 0)


def _raise_value_error() -> None:
    raise ValueError("bad marshal data")


def _capture() -> BaseException:
    try:
        _raise_value_error()
    except ValueError as error:
        return error
    raise AssertionError("未捕获到异常")  # pragma: no cover


def test_fingerprint_is_stable_for_same_type_and_location() -> None:
    first = fault_from_exception(_capture())
    second = fault_from_exception(_capture())

    assert first.fingerprint == second.fingerprint
    assert first.exc_type == "ValueError"
    assert "test_diagnostics_throttle.py" in first.location


def test_fingerprint_differs_by_location() -> None:
    assert make_fingerprint("ValueError", "a.py:1") != make_fingerprint("ValueError", "a.py:2")


def test_fingerprint_differs_by_exception_type() -> None:
    assert make_fingerprint("ValueError", "a.py:1") != make_fingerprint("OSError", "a.py:1")


def test_fingerprint_excludes_message_text() -> None:
    """指纹只取异常类型与堆栈顶部位置，消息里的用户数据不参与，也不会泄漏。"""
    fault = fault_from_exception(_capture())

    assert "bad marshal data" not in fault.fingerprint


def _record_times(state: ThrottleState, fingerprint: str, moments: list[datetime]):
    decisions = []
    for moment in moments:
        decision = record_fault(state, fingerprint, moment)
        state = decision.state
        decisions.append(decision)
    return state, decisions


def test_does_not_trigger_before_threshold() -> None:
    # Arrange
    moments = [START + timedelta(minutes=index) for index in range(BURST_THRESHOLD - 1)]

    # Act
    _, decisions = _record_times(ThrottleState(), "fp1", moments)

    # Assert
    assert not any(decision.should_collect for decision in decisions)
    assert decisions[-1].reason == "未达阈值"


def test_triggers_on_third_hit_within_window() -> None:
    moments = [START, START + timedelta(minutes=2), START + timedelta(minutes=4)]

    _, decisions = _record_times(ThrottleState(), "fp1", moments)

    assert [decision.should_collect for decision in decisions] == [False, False, True]
    assert decisions[-1].hits == BURST_THRESHOLD


def test_does_not_trigger_when_hits_fall_outside_window() -> None:
    """第 1 次与第 3 次相隔超过 10 分钟，窗口内只剩 2 次。"""
    moments = [START, START + timedelta(minutes=9), START + timedelta(minutes=11)]

    _, decisions = _record_times(ThrottleState(), "fp1", moments)

    assert not any(decision.should_collect for decision in decisions)


def test_same_fingerprint_collects_at_most_once_per_day() -> None:
    state, _ = _record_times(ThrottleState(), "fp1", [START] * BURST_THRESHOLD)
    later = START + timedelta(hours=3)

    state, decisions = _record_times(state, "fp1", [later] * BURST_THRESHOLD)

    assert not any(decision.should_collect for decision in decisions)
    assert decisions[-1].reason == "同指纹今日已上报"


def test_same_fingerprint_collects_again_next_day() -> None:
    state, _ = _record_times(ThrottleState(), "fp1", [START] * BURST_THRESHOLD)
    tomorrow = START + timedelta(days=1)

    _, decisions = _record_times(state, "fp1", [tomorrow] * BURST_THRESHOLD)

    assert decisions[-1].should_collect


def test_instance_wide_daily_cap() -> None:
    # Arrange：先用满 DAILY_TOTAL 个不同指纹
    state = ThrottleState()
    for index in range(DAILY_TOTAL):
        state, decisions = _record_times(state, f"fp{index}", [START] * BURST_THRESHOLD)
        assert decisions[-1].should_collect

    # Act：第 DAILY_TOTAL+1 个指纹
    _, decisions = _record_times(state, "overflow", [START] * BURST_THRESHOLD)

    # Assert
    assert not decisions[-1].should_collect
    assert decisions[-1].reason == "今日上报已达上限"


def test_daily_cap_resets_next_day() -> None:
    state = ThrottleState()
    for index in range(DAILY_TOTAL):
        state, _ = _record_times(state, f"fp{index}", [START] * BURST_THRESHOLD)
    tomorrow = START + timedelta(days=1)

    _, decisions = _record_times(state, "fresh", [tomorrow] * BURST_THRESHOLD)

    assert decisions[-1].should_collect


def test_record_fault_returns_new_state_without_mutating() -> None:
    original = ThrottleState()

    decision = record_fault(original, "fp1", START)

    assert original.occurrences == {}
    assert decision.state is not original
    assert decision.state.occurrences["fp1"] == (START,)


def test_state_survives_serialization_roundtrip() -> None:
    """崩溃重启后限流要继续生效，所以状态必须能落盘再读回。"""
    state, _ = _record_times(ThrottleState(), "fp1", [START] * BURST_THRESHOLD)

    restored = load_state(serialize_state(state))
    _, decisions = _record_times(restored, "fp1", [START + timedelta(hours=1)] * BURST_THRESHOLD)

    assert not any(decision.should_collect for decision in decisions)


def test_load_state_tolerates_broken_payload() -> None:
    assert load_state({"occurrences": "坏数据", "daily_count": None}) == ThrottleState()
