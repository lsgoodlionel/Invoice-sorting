"""登录账号的导入边界（账本搬迁设计 3.1）。

合并不导入、SaaS 不导入、预览分区与警告、旧包照常、命令行。

测试数据全部虚构。
"""

import json

import pytest
from fastapi.testclient import TestClient

from invoice_sorting import main
from invoice_sorting.control.repository import create_tenant
from invoice_sorting.main import create_app
from invoice_sorting.migration.accounts_report import NOTE_RESTORE, WARN_NO_ADMIN
from invoice_sorting.migration.export import export_tenant
from invoice_sorting.migration.merge import preview_import, run_import
from invoice_sorting.migration.replace_preview import run_replace
from tests.accounts_helpers import (
    ALICE_PASSWORD,
    NEW_ADMIN_PASSWORD,
    OLD_ADMIN_PASSWORD,
    can_login,
    export_with_accounts,
    find_account,
    machine,
    prepare_new_machine,
    prepare_old_machine,
    read_package_accounts,
    replace_import,
    rewrite_accounts,
)
from tests.conftest import make_saas_settings
from tests.migration_helpers import seed_tenant_data


@pytest.fixture
def backup(tmp_path):
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


def _args(app, archive, slug="default"):
    return (app.state.tenants, app.state.control_session_factory, archive, slug)


def _accounts_item(report: dict) -> dict:
    return next(item for item in report["items"] if item["key"] == "accounts")


def test_merge_never_imports_accounts(new_app, backup):
    report = run_import(*_args(new_app, backup), "merge")

    assert report["accounts"] == {
        "count": 3,
        "will_restore": False,
        "note": "包内含 3 个账号，合并模式不导入账号",
    }
    assert can_login(new_app, "admin", NEW_ADMIN_PASSWORD)
    assert not can_login(new_app, "alice", ALICE_PASSWORD)  # 至多是停用的占位账号
    assert all(item["key"] != "accounts" for item in report["items"])


def test_merge_preview_explains_accounts_are_skipped(new_app, backup):
    report = preview_import(*_args(new_app, backup), "merge")

    assert report["accounts"]["note"] == "包内含 3 个账号，合并模式不导入账号"
    assert report["source"]["has_accounts"] is True
    assert report["source"]["account_count"] == 3


def test_replace_preview_lists_accounts_and_warns(new_app, backup):
    report = preview_import(*_args(new_app, backup), "replace")

    item = _accounts_item(report)
    details = {row["label"]: (row["action"], row["reason"]) for row in item["details"]}
    assert report["accounts"] == {"count": 3, "will_restore": True, "note": NOTE_RESTORE}
    assert (item["added"], item["updated"]) == (2, 1)
    admin_action, admin_reason = details["admin（管理员）"]
    assert admin_action == "updated" and "更新密码" in admin_reason
    assert details["alice（成员）"][0] == "added"
    assert details["bob（管理员）"][0] == "added"
    assert details["carol（成员）"] == ("deleted", "备份里没有的本地账号，删除")
    assert item["deleted"] == 1
    assert "本地多出的账号将被删除" in report["accounts"]["note"]
    assert can_login(new_app, "admin", NEW_ADMIN_PASSWORD)  # 预览不写入


def test_replace_preview_warns_when_no_admin_would_remain(new_app, backup, tmp_path):
    def disable_admins(rows):
        return [{**row, "is_active": row["role"] != "admin"} for row in rows]

    broken = rewrite_accounts(backup, tmp_path / "无管理员.zip", disable_admins)

    report = preview_import(*_args(new_app, broken), "replace")

    assert WARN_NO_ADMIN in report["warnings"]


def test_replace_preview_keeps_the_actor(new_app, backup):
    carol = find_account(new_app, "carol")

    report = preview_import(*_args(new_app, backup), "replace", actor_id=carol.id)

    details = {row["label"]: row for row in _accounts_item(report)["details"]}
    assert details["carol（成员）"]["action"] == "skipped"
    assert "执行导入的管理员本人" in details["carol（成员）"]["reason"]


def test_replace_report_has_accounts_section(new_app, backup):
    report = run_replace(*_args(new_app, backup))

    assert _accounts_item(report)["added"] == 2
    assert _accounts_item(report)["deleted"] == 1
    assert report["accounts"]["will_restore"] is True


def test_reports_never_contain_password_hashes(new_app, backup):
    hashes = [row["password_hash"] for row in read_package_accounts(backup)]

    texts = [
        json.dumps(preview_import(*_args(new_app, backup), mode), ensure_ascii=False)
        for mode in ("merge", "replace")
    ]

    assert all(value not in text for value in hashes for text in texts)


def test_package_without_accounts_leaves_accounts_alone(new_app, tmp_path):
    source = machine(tmp_path / "旧版")
    with TestClient(source) as client:
        prepare_old_machine(client)
    legacy = tmp_path / "旧包.zip"
    export_tenant(source.state.tenants.get("default"), legacy, tenant_name="虚构旧包")

    report = run_replace(*_args(new_app, legacy))

    assert "accounts" not in report
    assert can_login(new_app, "admin", NEW_ADMIN_PASSWORD)
    assert not can_login(new_app, "admin", OLD_ADMIN_PASSWORD)


@pytest.fixture
def saas_target(tmp_path):
    app = create_app(make_saas_settings(tmp_path / "平台"))
    with app.state.control_session_factory() as control:
        create_tenant(control, "t1", "虚构账套")
        control.commit()
    return app


def test_saas_target_replace_does_not_import_accounts(saas_target, backup):
    preview = preview_import(*_args(saas_target, backup, "t1"), "replace")
    report = run_replace(*_args(saas_target, backup, "t1"))

    note = "包内含 3 个账号，SaaS 部署的账号由平台统一管理，覆盖模式不导入账号"
    assert preview["accounts"] == {"count": 3, "will_restore": False, "note": note}
    assert report["accounts"]["note"] == note
    assert all(item["key"] != "accounts" for item in report["items"])
    alice = find_account(saas_target, "alice")
    backup_hash = next(r["password_hash"] for r in read_package_accounts(backup) if r["id"] == 2)
    assert alice is None or alice.password_hash != backup_hash


def test_cli_replace_restores_accounts(new_app, backup, monkeypatch, capsys):
    settings = new_app.state.settings
    monkeypatch.setenv("INVOICE_SORTING_DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("INVOICE_SORTING_WATCH_INBOX", "false")

    main.run(["import-tenant", "--in", str(backup), "--mode", "replace", "--overwrite"])

    printed = capsys.readouterr().out
    assert "登录账号：新建 2、更新 1" in printed
    assert "账号：登录账号已恢复" in printed
    assert can_login(new_app, "alice", ALICE_PASSWORD)


def test_cli_merge_does_not_import_accounts(new_app, backup, monkeypatch, capsys):
    monkeypatch.setenv("INVOICE_SORTING_DATA_DIR", str(new_app.state.settings.data_dir))
    monkeypatch.setenv("INVOICE_SORTING_WATCH_INBOX", "false")

    main.run(["import-tenant", "--in", str(backup)])

    assert "账号：包内含 3 个账号，合并模式不导入账号" in capsys.readouterr().out
    assert can_login(new_app, "admin", NEW_ADMIN_PASSWORD)


def test_replace_import_helper_matches_cli_semantics(new_app, backup):
    """命令行与网页共用 import_tenant：同一个包两次覆盖结果一致（幂等）。"""
    replace_import(new_app, backup)
    replace_import(new_app, backup)

    assert can_login(new_app, "admin", OLD_ADMIN_PASSWORD)
    assert find_account(new_app, "alice").id == 2
