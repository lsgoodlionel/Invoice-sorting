"""用量统计：成员数、当月新增记录数（Asia/Shanghai 月界），以及字节换算。"""

from datetime import date, datetime

import pytest

from invoice_sorting.config import Settings
from invoice_sorting.control.database import (
    create_control_engine,
    init_control_db,
    make_control_session_factory,
)
from invoice_sorting.control.repository import (
    create_account,
    create_tenant,
    ensure_membership,
)
from invoice_sorting.db.models import TZ, Base, Expense
from invoice_sorting.db.session import create_db_engine, make_session_factory
from invoice_sorting.quota.usage import (
    count_active_members,
    count_expenses_created,
    megabytes,
    month_window,
)


@pytest.fixture
def control(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    engine = create_control_engine(settings)
    init_control_db(engine)
    factory = make_control_session_factory(engine)
    try:
        with factory() as db:
            yield db
    finally:
        engine.dispose()


@pytest.fixture
def business(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'invoice.db'}")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            yield db
    finally:
        engine.dispose()


def add_expense(db, created_at: datetime) -> None:
    db.add(Expense(spent_on=date(2026, 9, 1), amount_cents=100, created_at=created_at))
    db.commit()


def test_month_window_covers_the_shanghai_month(tmp_path):
    start, end = month_window(datetime(2026, 9, 20, 10, 0, tzinfo=TZ))

    assert start == datetime(2026, 9, 1, 0, 0)
    assert end == datetime(2026, 10, 1, 0, 0)


def test_month_window_rolls_over_december():
    start, end = month_window(datetime(2026, 12, 31, 23, 59, tzinfo=TZ))

    assert (start.year, start.month) == (2026, 12)
    assert (end.year, end.month) == (2027, 1)


def test_count_expenses_created_only_counts_the_current_month(business):
    moment = datetime(2026, 9, 20, 10, 0, tzinfo=TZ)
    add_expense(business, datetime(2026, 8, 31, 23, 59, 59, tzinfo=TZ))  # 上月最后一刻
    add_expense(business, datetime(2026, 9, 1, 0, 0, 0, tzinfo=TZ))  # 本月第一刻
    add_expense(business, datetime(2026, 9, 20, 9, 0, 0, tzinfo=TZ))
    add_expense(business, datetime(2026, 10, 1, 0, 0, 0, tzinfo=TZ))  # 下月第一刻

    assert count_expenses_created(business, moment) == 2


def test_count_expenses_created_includes_deleted_records(business):
    moment = datetime(2026, 9, 20, 10, 0, tzinfo=TZ)
    business.add(
        Expense(
            spent_on=date(2026, 9, 1),
            amount_cents=100,
            created_at=datetime(2026, 9, 2, tzinfo=TZ),
            deleted=True,
        )
    )
    business.commit()

    assert count_expenses_created(business, moment) == 1


def test_count_active_members_ignores_disabled_accounts_and_memberships(control):
    tenant = create_tenant(control, "alpha", "阿尔法")
    other = create_tenant(control, "beta", "贝塔")
    for index in range(3):
        account = create_account(control, f"user{index}", f"用户{index}")
        ensure_membership(control, account.id, tenant.id)
    disabled = create_account(control, "stopped", "已停用")
    disabled.is_active = False
    ensure_membership(control, disabled.id, tenant.id)
    left = create_account(control, "left", "已移出")
    ensure_membership(control, left.id, tenant.id, is_active=False)
    outsider = create_account(control, "outsider", "别的账套")
    ensure_membership(control, outsider.id, other.id)
    control.flush()

    assert count_active_members(control, tenant.id) == 3


@pytest.mark.parametrize(
    ("byte_count", "expected"), [(0, 0), (1024 * 1024 - 1, 0), (1024 * 1024, 1), (3_500_000, 3)]
)
def test_megabytes_rounds_down(byte_count, expected):
    assert megabytes(byte_count) == expected
