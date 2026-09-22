"""可复用的删除账号（users/deletion.py）：控制库删账号，业务库镜像保留并标记已删除。测试数据全部虚构。"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from invoice_sorting.common.errors import AppError
from invoice_sorting.control.models import Account, ControlAuthSession, Invite, Membership
from invoice_sorting.control.repository import find_tenant
from invoice_sorting.db.models import User
from invoice_sorting.users.deletion import delete_account
from tests.accounts_helpers import CAROL_PASSWORD, can_login, find_account, machine
from tests.auth_helpers import create_user, login, setup_password
from tests.platform_helpers import make_saas_app
from tests.tenancy_helpers import add_member

ADMIN_PASSWORD = "admin-pass-for-delete"


@pytest.fixture
def app(tmp_path):
    app = machine(tmp_path / "删除")
    with TestClient(app) as client:
        setup_password(client, ADMIN_PASSWORD)
        create_user(client, "carol", password=CAROL_PASSWORD, display_name="虚构丙")
    return app


def _delete(app, account_id: int, actor_id: int | None, slug: str = "default"):
    with app.state.control_session_factory() as control:
        tenant_id = find_tenant(control, slug).id
        with app.state.tenants.get(slug).session_factory() as business:
            result = delete_account(
                control, business, account_id, actor_id=actor_id, tenant_id=tenant_id
            )
            business.commit()
        control.commit()
    return result


def test_deletes_account_membership_sessions_and_marks_mirror(app):
    carol_id = find_account(app, "carol").id
    admin_id = find_account(app, "admin").id
    with TestClient(app) as client:
        assert login(client, CAROL_PASSWORD, "carol").status_code == 200
    with app.state.control_session_factory() as control:
        tenant_id = find_tenant(control, "default").id
        control.add(Invite(code="虚构邀请码", tenant_id=tenant_id, used_by=carol_id))
        control.commit()

    result = _delete(app, carol_id, admin_id)

    assert result.is_account_removed and result.username == "carol"
    assert not can_login(app, "carol", CAROL_PASSWORD)
    with app.state.control_session_factory() as control:
        assert control.get(Account, carol_id) is None
        assert not control.scalars(
            select(Membership).where(Membership.account_id == carol_id)
        ).all()
        assert not control.scalars(
            select(ControlAuthSession).where(ControlAuthSession.account_id == carol_id)
        ).all()
        assert control.scalar(select(Invite.used_by)) is None
    with app.state.tenants.get("default").session_factory() as db:
        mirror = db.get(User, carol_id)
    assert mirror.display_name == "虚构丙"
    assert mirror.is_deleted and not mirror.is_active and mirror.deleted_at is not None


def test_cannot_delete_self(app):
    admin_id = find_account(app, "admin").id

    with pytest.raises(AppError, match="不能删除自己"):
        _delete(app, admin_id, admin_id)

    assert can_login(app, "admin", ADMIN_PASSWORD)


def test_account_in_another_tenant_is_only_removed_from_this_one(tmp_path):
    app = make_saas_app(tmp_path)
    shared = add_member(app, "alpha", "shared-user")
    add_member(app, "beta", "shared-user")

    result = _delete(app, shared, actor_id=None, slug="alpha")

    assert not result.is_account_removed
    with app.state.control_session_factory() as control:
        assert control.get(Account, shared) is not None
        tenants = {
            m.tenant_id
            for m in control.scalars(select(Membership).where(Membership.account_id == shared))
        }
        assert tenants == {find_tenant(control, "beta").id}
