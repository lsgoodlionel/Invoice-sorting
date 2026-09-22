"""单账套整套覆盖恢复登录账号（账本搬迁设计 3.1）：换机后账号与密码随备份回来。

场景：旧机器有 admin、alice（成员）、bob（管理员）并导出备份；新机器 admin 用另一个密码，
另有本地独有成员 carol，恰好占用了备份里 alice 的 id 2。测试数据全部虚构。
"""

import logging
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from invoice_sorting.common.errors import AppError
from invoice_sorting.db.models import Expense, User
from invoice_sorting.migration import restore
from invoice_sorting.migration.accounts_file import read_accounts
from invoice_sorting.migration.accounts_restore import restore_accounts
from invoice_sorting.migration.errors import ImportRejectedError
from invoice_sorting.migration.restore import read_manifest
from tests.accounts_helpers import (
    ALICE_PASSWORD,
    BOB_PASSWORD,
    CAROL_PASSWORD,
    KEEPER_PASSWORD,
    NEW_ADMIN_PASSWORD,
    OLD_ADMIN_PASSWORD,
    can_login,
    export_with_accounts,
    find_account,
    machine,
    mirror_user,
    prepare_new_machine,
    prepare_old_machine,
    read_package_accounts,
    replace_import,
    rewrite_accounts,
    session_account_ids,
)
from tests.auth_helpers import create_user, login, setup_password
from tests.migration_helpers import SAMPLE_EXPENSES, seed_tenant_data


@pytest.fixture
def backup(tmp_path):
    """旧机器的备份包（含虚构记录与账号）。"""
    app = machine(tmp_path / "旧机器")
    with TestClient(app) as client:
        prepare_old_machine(client)
    with app.state.tenants.get("default").session_factory() as db:
        seed_tenant_data(db, app.state.settings, tmp_path / "来源")
    return export_with_accounts(app, tmp_path / "备份.zip")


@pytest.fixture
def new_app(tmp_path):
    app = machine(tmp_path / "新机器")
    with TestClient(app) as client:
        prepare_new_machine(client)
    return app


def _expenses(app) -> int:
    with app.state.tenants.get("default").session_factory() as db:
        return len(list(db.scalars(select(Expense))))


def test_same_name_admin_gets_backup_password(new_app, backup):
    replace_import(new_app, backup)

    assert can_login(new_app, "admin", OLD_ADMIN_PASSWORD)
    assert not can_login(new_app, "admin", NEW_ADMIN_PASSWORD)


def test_missing_accounts_are_created_with_backup_ids(new_app, backup):
    backup_ids = {row["username"]: row["id"] for row in read_package_accounts(backup)}

    replace_import(new_app, backup)

    alice, bob = find_account(new_app, "alice"), find_account(new_app, "bob")
    assert can_login(new_app, "alice", ALICE_PASSWORD)
    assert can_login(new_app, "bob", BOB_PASSWORD)
    assert (alice.id, bob.id) == (backup_ids["alice"], backup_ids["bob"])
    assert mirror_user(new_app, alice.id).username == "alice"  # User.id == Account.id


def test_local_only_account_is_deleted(new_app, backup):
    carol_before = find_account(new_app, "carol").id
    assert carol_before == 2  # 与备份里 alice 的 id 冲突

    replace_import(new_app, backup)

    assert find_account(new_app, "carol") is None
    assert not can_login(new_app, "carol", CAROL_PASSWORD)
    assert find_account(new_app, "alice").id == 2


def test_actor_missing_from_backup_is_kept_and_moved_off_conflicting_id(tmp_path, backup):
    app = machine(tmp_path / "执行者机器")
    with TestClient(app) as client:
        setup_password(client, NEW_ADMIN_PASSWORD)
        create_user(client, "keeper", password=KEEPER_PASSWORD, role="admin")
    keeper_before = find_account(app, "keeper").id
    assert keeper_before == 2

    replace_import(app, backup, actor_id=keeper_before)

    keeper = find_account(app, "keeper")
    assert keeper.id > 3 and can_login(app, "keeper", KEEPER_PASSWORD)
    mirror = mirror_user(app, keeper.id)
    assert mirror is not None and mirror.username == "keeper"


def test_changed_and_deleted_accounts_lose_sessions_actor_keeps_his(tmp_path, backup):
    app = machine(tmp_path / "会话机器")
    with TestClient(app) as setup:
        setup_password(setup, NEW_ADMIN_PASSWORD)
        create_user(setup, "keeper", password=KEEPER_PASSWORD, role="admin")
        create_user(setup, "carol", password=CAROL_PASSWORD)
    with TestClient(app) as admin, TestClient(app) as carol, TestClient(app) as keeper:
        assert login(admin, NEW_ADMIN_PASSWORD).status_code == 200
        assert login(carol, CAROL_PASSWORD, "carol").status_code == 200
        assert login(keeper, KEEPER_PASSWORD, "keeper").status_code == 200

        replace_import(app, backup, actor_id=find_account(app, "keeper").id)

        states = [c.get("/api/auth/status").json()["data"] for c in (admin, carol, keeper)]
    assert [state["authenticated"] for state in states] == [False, False, True]
    assert find_account(app, "admin").id not in session_account_ids(app)


def test_deleted_account_mirror_is_kept_and_marked(new_app, tmp_path):
    """备份里的业务库有 carol 的历史镜像，但 accounts.json 里没有她：删除后镜像保留并标记。"""
    source = machine(tmp_path / "有历史的旧机器")
    with TestClient(source) as client:
        prepare_old_machine(client)
        create_user(client, "carol", password=CAROL_PASSWORD, display_name="虚构丙")
    full = export_with_accounts(source, tmp_path / "含丙.zip")
    trimmed = rewrite_accounts(
        full, tmp_path / "去掉丙.zip", lambda rows: [r for r in rows if r["username"] != "carol"]
    )

    replace_import(new_app, trimmed)

    with new_app.state.tenants.get("default").session_factory() as db:
        row = db.scalar(select(User).where(User.username == "carol"))
    assert find_account(new_app, "carol") is None
    assert row is not None and row.is_deleted and not row.is_active
    assert row.display_name == "虚构丙" and row.deleted_at is not None
    restart = machine(tmp_path / "新机器")  # 重启后的启动迁移不会把她“复活”
    with TestClient(restart):
        assert find_account(restart, "carol") is None


def test_business_data_is_replaced_together_with_accounts(new_app, backup):
    replace_import(new_app, backup)

    assert _expenses(new_app) == len(SAMPLE_EXPENSES)


def _without_usable_admin(rows: list[dict]) -> list[dict]:
    return [{**row, "is_active": False} if row["role"] == "admin" else row for row in rows]


def test_no_usable_admin_aborts_before_writing(new_app, backup, tmp_path):
    broken = rewrite_accounts(backup, tmp_path / "无管理员.zip", _without_usable_admin)
    backups_dir = new_app.state.settings.backup_dir

    with pytest.raises(ImportRejectedError, match="没有可用的管理员"):
        replace_import(new_app, broken)

    assert _expenses(new_app) == 0  # 新机器原本没有记录，账本未被替换
    assert can_login(new_app, "admin", NEW_ADMIN_PASSWORD)
    assert not list(backups_dir.glob("覆盖前备份_*.zip"))  # 连覆盖前备份都还没做


def test_failure_after_unpack_rolls_back_data_and_accounts(new_app, backup, monkeypatch):
    def broken_restore(*args, **kwargs):
        raise RuntimeError("虚构的写入故障")

    monkeypatch.setattr(restore, "restore_accounts", broken_restore)

    with pytest.raises(AppError, match="已回滚"):
        replace_import(new_app, backup)

    assert _expenses(new_app) == 0  # 业务数据已用覆盖前备份还原
    assert can_login(new_app, "admin", NEW_ADMIN_PASSWORD)
    assert find_account(new_app, "alice") is None


def test_logs_never_contain_password_hashes(new_app, backup, caplog):
    hashes = [row["password_hash"] for row in read_package_accounts(backup)]
    caplog.set_level(logging.DEBUG)

    replace_import(new_app, backup)

    assert all(value and value not in caplog.text for value in hashes)
    assert "已恢复登录账号 3 个" in caplog.text


def test_restore_on_same_machine_brings_old_password_back(tmp_path):
    app = machine(tmp_path / "本机")
    with TestClient(app) as client:
        prepare_old_machine(client)
        package = export_with_accounts(app, tmp_path / "备份.zip")
        changed = client.post(
            "/api/auth/password",
            json={"current_password": OLD_ADMIN_PASSWORD, "new_password": NEW_ADMIN_PASSWORD},
        )
        assert changed.status_code == 200, changed.text

    replace_import(app, package)

    assert can_login(app, "admin", OLD_ADMIN_PASSWORD)
    assert find_account(app, "alice").id == 2


def test_transaction_recheck_rolls_back_control_changes(new_app, backup):
    """绕过解包前检查直接写回：事务内复核不通过时控制库整体回滚。"""
    accounts = read_accounts(backup, read_manifest(backup))
    records = tuple(
        replace(record, is_active=record.role != "admin") for record in accounts.accounts
    )
    disabled = replace(accounts, accounts=records)

    with pytest.raises(ImportRejectedError, match="没有可用的管理员"):
        restore_accounts(new_app.state.control_session_factory, 1, disabled, {})

    assert can_login(new_app, "admin", NEW_ADMIN_PASSWORD)
    assert find_account(new_app, "carol").id == 2  # 删除也一并回滚
    assert find_account(new_app, "alice") is None


def test_first_import_without_backup_is_discarded_on_failure(tmp_path, backup, monkeypatch):
    """导入前还没有数据库（没有覆盖前备份）：写回账号失败时撤掉刚解出的数据。"""
    app = machine(tmp_path / "空机器")
    with TestClient(app) as client:
        setup_password(client, NEW_ADMIN_PASSWORD)

    def broken_restore(*args, **kwargs):
        raise RuntimeError("虚构的写入故障")

    monkeypatch.setattr(restore, "restore_accounts", broken_restore)
    target = app.state.settings.for_tenant("copy1")

    with pytest.raises(AppError, match="已回滚"):
        replace_import(app, backup, slug="copy1")

    assert not target.db_path.exists()
    assert not any(target.library_dir.rglob("*.pdf"))
    assert can_login(app, "admin", NEW_ADMIN_PASSWORD)
