"""租户状态与额度判定（纯函数）：只读原因、各项上限的命中与文案。"""

from datetime import date

import pytest

from invoice_sorting.control.models import (
    TENANT_STATUS_ACTIVE,
    TENANT_STATUS_CLOSED,
    TENANT_STATUS_SUSPENDED,
)
from invoice_sorting.quota.constants import (
    KIND_EXPENSES,
    KIND_STORAGE,
    KIND_USERS,
    REASON_CLOSED,
    REASON_EXPIRED,
    REASON_SUSPENDED,
)
from invoice_sorting.quota.plans import PlanLimits
from invoice_sorting.quota.state import build_lines, exceeded_message, limit_line, readonly_notice

TODAY = date(2026, 9, 20)
PLAN = PlanLimits(
    code="team", name="团队版", max_users=3, max_storage_mb=10, max_expenses_per_month=5
)


def test_active_tenant_without_expiry_is_writable():
    notice = readonly_notice(TENANT_STATUS_ACTIVE, None, TODAY)

    assert notice.reason == ""
    assert notice.message == ""
    assert notice.is_readonly is False


def test_suspended_tenant_is_readonly_with_its_own_wording():
    notice = readonly_notice(TENANT_STATUS_SUSPENDED, None, TODAY)

    assert notice.reason == REASON_SUSPENDED
    assert "账套已停用" in notice.message
    assert "只读" in notice.message and "导出" in notice.message


def test_closed_tenant_is_readonly():
    notice = readonly_notice(TENANT_STATUS_CLOSED, None, TODAY)

    assert notice.reason == REASON_CLOSED
    assert "账套已关闭" in notice.message


def test_expired_subscription_is_readonly_and_names_the_day():
    notice = readonly_notice(TENANT_STATUS_ACTIVE, date(2026, 9, 19), TODAY)

    assert notice.reason == REASON_EXPIRED
    assert "订阅已到期" in notice.message
    assert "2026-09-19" in notice.message


def test_expiry_day_itself_is_still_writable():
    assert readonly_notice(TENANT_STATUS_ACTIVE, TODAY, TODAY).is_readonly is False


def test_status_wins_over_expiry_when_both_apply():
    notice = readonly_notice(TENANT_STATUS_SUSPENDED, date(2026, 1, 1), TODAY)

    assert notice.reason == REASON_SUSPENDED


@pytest.mark.parametrize(
    ("used", "is_exceeded", "remaining"),
    [(0, False, 3), (2, False, 1), (3, True, 0), (5, True, 0)],
)
def test_limit_line_marks_reaching_the_cap_as_exceeded(used, is_exceeded, remaining):
    line = limit_line(PLAN, KIND_USERS, used)

    assert (line.is_exceeded, line.remaining) == (is_exceeded, remaining)
    assert (line.limit, line.used, line.unit) == (3, used, "人")


def test_unlimited_line_is_never_exceeded():
    plan = PlanLimits(code="pro", name="旗舰版", max_users=0)

    line = limit_line(plan, KIND_USERS, 9999)

    assert line.is_unlimited is True
    assert line.is_exceeded is False
    assert line.remaining is None


def test_build_lines_covers_all_three_items():
    lines = build_lines(PLAN, users=1, storage_mb=2, expenses=3)

    assert [line.key for line in lines] == [KIND_USERS, KIND_STORAGE, KIND_EXPENSES]
    assert [line.used for line in lines] == [1, 2, 3]


@pytest.mark.parametrize(
    ("kind", "used", "keyword", "unit"),
    [
        (KIND_USERS, 3, "成员数量", "人"),
        (KIND_STORAGE, 10, "存储空间", "MB"),
        (KIND_EXPENSES, 5, "本月新增记录", "条"),
    ],
)
def test_exceeded_message_names_item_limit_and_current(kind, used, keyword, unit):
    message = exceeded_message(PLAN, kind, used)

    assert keyword in message
    assert "团队版" in message
    assert f"{used}" in message and unit in message
    assert "上限" in message
