"""触发阈值与限流（设计《日志与故障上报》5.3 与 5.4）。

纯状态机，不碰文件与网络，便于测试：

- 同一指纹在 `WINDOW_MINUTES` 分钟内累计 `BURST_THRESHOLD` 次才触发一次打包；
- 同一指纹每天最多 `DAILY_PER_FINGERPRINT` 次；
- 全实例每天最多 `DAILY_TOTAL` 次。

状态可序列化落盘：崩溃重启循环下计数不会因为进程重启而清零。
所有更新都返回**新的** ThrottleState，不修改入参。
"""

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any

WINDOW_MINUTES = 10
BURST_THRESHOLD = 3
DAILY_PER_FINGERPRINT = 1
DAILY_TOTAL = 5
MAX_TRACKED_FINGERPRINTS = 200

REASON_BELOW_THRESHOLD = "未达阈值"
REASON_FINGERPRINT_DONE = "同指纹今日已上报"
REASON_DAILY_FULL = "今日上报已达上限"
REASON_TRIGGERED = "已触发"


@dataclass(frozen=True)
class ThrottleState:
    """窗口内的命中时刻 + 今日已上报的指纹 + 今日总次数。"""

    occurrences: dict[str, tuple[datetime, ...]] = field(default_factory=dict)
    collected_on: dict[str, str] = field(default_factory=dict)
    daily_date: str = ""
    daily_count: int = 0

    def remaining_today(self) -> int:
        return max(DAILY_TOTAL - self.daily_count, 0)


@dataclass(frozen=True)
class ThrottleDecision:
    """一次记录的结果：新的状态、是否应当打包、以及未触发的原因。"""

    state: ThrottleState
    should_collect: bool
    reason: str
    hits: int


def record_fault(state: ThrottleState, fingerprint: str, moment: datetime) -> ThrottleDecision:
    """记录一次故障命中，返回是否应当生成诊断包。"""
    today = moment.date().isoformat()
    rolled = _roll_day(state, today)
    window = _recent_hits(rolled.occurrences.get(fingerprint, ()), moment)
    hits = len(window)
    updated = _with_occurrences(rolled, fingerprint, window)
    reason = _blocking_reason(updated, fingerprint, hits, today)
    if reason is not None:
        return ThrottleDecision(updated, False, reason, hits)
    return ThrottleDecision(
        _mark_collected(updated, fingerprint, today), True, REASON_TRIGGERED, hits
    )


def _blocking_reason(state: ThrottleState, fingerprint: str, hits: int, today: str) -> str | None:
    if hits < BURST_THRESHOLD:
        return REASON_BELOW_THRESHOLD
    if state.collected_on.get(fingerprint) == today:
        return REASON_FINGERPRINT_DONE
    if state.daily_count >= DAILY_TOTAL:
        return REASON_DAILY_FULL
    return None


def _roll_day(state: ThrottleState, today: str) -> ThrottleState:
    """跨天时重置每日计数与“今日已上报”记录。"""
    if state.daily_date == today:
        return state
    return replace(state, daily_date=today, daily_count=0, collected_on={})


def _recent_hits(existing: tuple[datetime, ...], moment: datetime) -> tuple[datetime, ...]:
    earliest = moment - timedelta(minutes=WINDOW_MINUTES)
    return (*(hit for hit in existing if hit > earliest), moment)


def _with_occurrences(
    state: ThrottleState, fingerprint: str, window: tuple[datetime, ...]
) -> ThrottleState:
    """整体替换字典；顺带丢掉最久未出现的指纹，避免长期运行后无限增长。"""
    merged = {**state.occurrences, fingerprint: window}
    if len(merged) > MAX_TRACKED_FINGERPRINTS:
        newest = sorted(merged.items(), key=lambda item: max(item[1]), reverse=True)
        merged = dict(newest[:MAX_TRACKED_FINGERPRINTS])
    return replace(state, occurrences=merged)


def _mark_collected(state: ThrottleState, fingerprint: str, today: str) -> ThrottleState:
    """触发后清空该指纹的窗口，下一轮重新累计。"""
    return replace(
        state,
        occurrences={**state.occurrences, fingerprint: ()},
        collected_on={**state.collected_on, fingerprint: today},
        daily_date=today,
        daily_count=state.daily_count + 1,
    )


def serialize_state(state: ThrottleState) -> dict[str, Any]:
    """转成可写入 JSON 的结构（时间用 ISO 文本）。"""
    return {
        "occurrences": {
            key: [hit.isoformat() for hit in hits] for key, hits in state.occurrences.items()
        },
        "collected_on": dict(state.collected_on),
        "daily_date": state.daily_date,
        "daily_count": state.daily_count,
    }


def load_state(payload: Any) -> ThrottleState:
    """从落盘结构还原；任何字段损坏都退化为空状态，绝不抛错。"""
    if not isinstance(payload, dict):
        return ThrottleState()
    return ThrottleState(
        occurrences=_load_occurrences(payload.get("occurrences")),
        collected_on=_load_strings(payload.get("collected_on")),
        daily_date=_load_text(payload.get("daily_date")),
        daily_count=_load_count(payload.get("daily_count")),
    )


def _load_occurrences(raw: Any) -> dict[str, tuple[datetime, ...]]:
    if not isinstance(raw, dict):
        return {}
    return {key: _load_moments(value) for key, value in raw.items() if isinstance(key, str)}


def _load_moments(raw: Any) -> tuple[datetime, ...]:
    if not isinstance(raw, list):
        return ()
    moments = []
    for item in raw:
        try:
            moments.append(datetime.fromisoformat(item))
        except (TypeError, ValueError):
            continue
    return tuple(moments)


def _load_strings(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    return {
        key: value for key, value in raw.items() if isinstance(key, str) and isinstance(value, str)
    }


def _load_text(raw: Any) -> str:
    return raw if isinstance(raw, str) else ""


def _load_count(raw: Any) -> int:
    return raw if isinstance(raw, int) and raw >= 0 else 0
