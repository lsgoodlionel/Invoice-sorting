"""账号恢复规划（纯计算）：去向分类、id 对齐与让位、可用管理员判断、会话失效范围。

测试数据全部虚构。
"""

from invoice_sorting.migration.accounts_file import AccountRecord
from invoice_sorting.migration.accounts_plan import IdMove, LocalAccount, build_plan, plan_section

HASH_A = "scrypt$n=16384,r=8,p=1$YQ==$YQ=="
HASH_B = "scrypt$n=16384,r=8,p=1$Yg==$Yg=="


def _record(account_id, username, role="member", **overrides) -> AccountRecord:
    values = {
        "id": account_id,
        "username": username,
        "display_name": username,
        "role": role,
        "is_active": True,
        "password_hash": HASH_A,
    }
    return AccountRecord(**{**values, **overrides})


def _local(account_id, username, role="member", **overrides) -> LocalAccount:
    values = {
        "id": account_id,
        "username": username,
        "display_name": username,
        "is_active": True,
        "role": role,
        "is_member_active": True,
        "password_hash": HASH_A,
    }
    return LocalAccount(**{**values, **overrides})


def test_classifies_created_updated_unchanged_and_deleted():
    records = [
        _record(1, "admin", "admin", password_hash=HASH_B),
        _record(2, "alice"),
        _record(3, "bob"),
    ]
    local = [_local(1, "admin", "admin"), _local(3, "bob"), _local(4, "carol")]

    plan = build_plan(records, local)
    section = plan_section(plan)

    assert (section.added, section.updated, section.skipped, section.deleted) == (1, 1, 1, 1)
    items = {item.label: (item.action, item.reason) for item in section.items}
    assert "更新密码" in items["admin（管理员）"][1]
    assert items["bob（成员）"] == ("skipped", "与本地一致")
    assert items["carol（成员）"] == ("deleted", "备份里没有的本地账号，删除")
    assert [a.username for a in plan.deleted] == ["carol"]
    assert plan.moves == ()


def test_actor_is_never_deleted():
    plan = build_plan(
        [_record(1, "admin", "admin")], [_local(1, "admin"), _local(4, "me", "admin")], actor_id=4
    )

    assert plan.deleted == ()
    assert [a.username for a in plan.kept] == ["me"]
    assert "执行导入的管理员本人" in plan_section(plan).items[-1].reason


def test_only_changed_accounts_lose_sessions():
    plan = build_plan(
        [_record(1, "admin", "admin", password_hash=HASH_B), _record(2, "bob"), _record(5, "new")],
        [_local(1, "admin", "admin"), _local(2, "bob")],
    )

    assert plan.invalidated_ids == (1, 5)


def test_matched_account_is_realigned_to_backup_id():
    plan = build_plan([_record(2, "alice")], [_local(1, "admin", "admin"), _local(5, "alice")])

    assert IdMove(5, 2) in plan.moves
    assert plan.invalidated_ids == (2,)


def test_deleted_account_needs_no_move_but_kept_actor_yields_id():
    local = [_local(1, "admin", "admin"), _local(2, "carol")]

    assert build_plan([_record(2, "alice")], local).moves == ()
    assert build_plan([_record(2, "alice")], local, actor_id=2).moves == (IdMove(2, 3),)


def test_swapped_ids_are_both_moved():
    plan = build_plan([_record(1, "b"), _record(2, "a")], [_local(1, "a"), _local(2, "b")])

    assert set(plan.moves) == {IdMove(1, 2), IdMove(2, 1)}


def test_local_only_account_aligns_to_same_name_in_new_business_db():
    plan = build_plan(
        [_record(1, "admin", "admin")],
        [_local(1, "admin", "admin"), _local(2, "carol")],
        business_users={1: "admin", 2: "dave", 7: "carol"},
        actor_id=2,
    )

    assert plan.moves == (IdMove(2, 7),)


def test_local_only_account_avoids_ids_used_by_business_history():
    plan = build_plan(
        [_record(1, "admin", "admin")],
        [_local(1, "admin", "admin"), _local(2, "carol")],
        business_users={1: "admin", 2: "dave"},
        actor_id=2,
    )

    assert plan.moves == (IdMove(2, 3),)


def test_usable_admin_rules():
    kept_admin = [_local(9, "keeper", "admin")]
    disabled = [_record(1, "admin", "admin", is_active=False)]

    assert build_plan(disabled, kept_admin, actor_id=9).has_usable_admin
    assert not build_plan(disabled, kept_admin).has_usable_admin  # 非执行者会被删除
    assert not build_plan(disabled, []).has_usable_admin
    assert not build_plan([_record(1, "boss", "admin", password_hash=None)], []).has_usable_admin
    # 内置 admin 尚未设密码：首次设置入口可用
    assert build_plan([_record(1, "admin", "admin", password_hash=None)], []).has_usable_admin
    matched_disabled = build_plan(disabled, [_local(1, "admin", "admin")])
    assert not matched_disabled.has_usable_admin  # 本地 admin 被备份值停用后不再算


def test_kept_account_outside_tenant_is_not_listed_but_may_move():
    plan = build_plan([_record(2, "alice")], [_local(2, "outsider", role=None)])

    assert plan.moves == (IdMove(2, 3),)
    assert all("outsider" not in item.label for item in plan_section(plan).items)
