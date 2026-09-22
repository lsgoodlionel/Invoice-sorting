"""账号 id 不复用（id_sequence）与已删除镜像行让出用户名（users/mirror.py）。测试数据全部虚构。"""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from invoice_sorting.control.database import init_control_db
from invoice_sorting.control.members import Member
from invoice_sorting.control.models import Account, Membership
from invoice_sorting.control.repository import create_account, create_tenant
from invoice_sorting.db.models import User, now
from invoice_sorting.db.session import create_db_engine, init_db
from invoice_sorting.users.deletion import delete_account
from invoice_sorting.users.mirror import released_username, sync_member_mirror


@pytest.fixture
def control(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'control.db'}")
    init_control_db(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def business(tmp_path):
    engine = create_db_engine(f"sqlite:///{tmp_path / 'tenant.db'}")
    init_db(engine)
    with Session(engine) as session:
        yield session


def _join(control: Session, username: str, tenant_id: int) -> Member:
    account = create_account(control, username, f"虚构{username}")
    membership = Membership(account_id=account.id, tenant_id=tenant_id, role="member")
    control.add(membership)
    control.flush()
    return Member(account=account, membership=membership)


def test_deleted_account_id_is_never_handed_out_again(control, business):
    tenant = create_tenant(control, "alpha", "虚构账套")
    first = _join(control, "carol", tenant.id)
    sync_member_mirror(business, first)

    delete_account(control, business, first.id, actor_id=None, tenant_id=tenant.id)
    again = _join(control, "carol", tenant.id)

    assert again.id == first.id + 1


def test_explicit_ids_are_respected_and_later_ids_go_past_them(control):
    create_account(control, "moved", "虚构迁移", account_id=40)

    fresh = create_account(control, "fresh", "虚构新人")

    assert fresh.id == 41


def test_accounts_created_in_one_flush_get_distinct_ids(control):
    control.add_all([Account(username="one"), Account(username="two")])
    control.flush()

    ids = list(control.scalars(select(Account.id).order_by(Account.id)))
    assert len(set(ids)) == 2


def test_deleted_mirror_releases_its_username_to_a_new_member(control, business):
    tenant = create_tenant(control, "alpha", "虚构账套")
    business.add(
        User(id=7, username="carol", display_name="虚构丙", is_deleted=True, created_at=now())
    )
    business.flush()
    member = _join(control, "carol", tenant.id)

    sync_member_mirror(business, member)

    old = business.get(User, 7)
    assert (old.username, old.display_name) == ("carol~7", "虚构丙")
    assert business.get(User, member.id).username == "carol"


def test_live_mirror_with_same_name_is_not_touched(control, business):
    tenant = create_tenant(control, "alpha", "虚构账套")
    business.add(User(id=7, username="carol", display_name="虚构丙", created_at=now()))
    business.flush()
    member = _join(control, "carol", tenant.id)

    with pytest.raises(IntegrityError):  # 与历史一致：未删除的重名行仍视为冲突
        sync_member_mirror(business, member)


def test_released_username_fits_the_column():
    name = released_username("x" * 32, 123456)

    assert len(name) == 32 and name.endswith("~123456")
