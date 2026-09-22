"""备份带账号（账本搬迁设计 2.1）：单账套的网页备份与命令行导出带 accounts.json，SaaS 不带。

测试数据全部虚构。
"""

import hashlib
import json
import logging
import zipfile

import pytest
from fastapi.testclient import TestClient

from invoice_sorting.migration.accounts_export import collect_accounts
from invoice_sorting.migration.ledger import LEDGER_NAME
from invoice_sorting.migration.ledger_backups import ledger_backups_dir
from invoice_sorting.migration.manifest import MANIFEST_NAME
from tests.accounts_helpers import (
    ACCOUNTS_MEMBER,
    export_with_accounts,
    find_account,
    machine,
    prepare_old_machine,
)
from tests.platform_helpers import make_saas_app
from tests.tenancy_helpers import host_headers, login_at

EXPORT = "/api/backup/export-tenant"


def _web_export(client: TestClient, headers=None) -> dict:
    response = client.post(EXPORT, json={"include_packages": False}, headers=headers)
    assert response.status_code == 200, response.text
    job = response.json()["data"]
    status = client.get(f"{job['download_url']}/status", headers=headers).json()["data"]
    assert status["status"] == "done", status["error"]
    return status


def _read(archive, name: str):
    with zipfile.ZipFile(archive) as package:
        return package.read(name) if name in package.namelist() else None


@pytest.fixture
def single(tmp_path):
    app = machine(tmp_path / "本机")
    with TestClient(app) as client:
        prepare_old_machine(client)
        yield app, client


def test_web_backup_contains_accounts_listed_and_checksummed(single):
    app, client = single

    job = _web_export(client)

    archive = ledger_backups_dir(app.state.settings) / job["file"]
    raw = _read(archive, ACCOUNTS_MEMBER)
    manifest = json.loads(_read(archive, MANIFEST_NAME))
    entry = next(row for row in manifest["files"] if row["path"] == "accounts.json")
    assert entry["size"] == len(raw)
    assert entry["sha256"] == hashlib.sha256(raw).hexdigest()
    assert manifest["sections"]["accounts"] == {"files": 1, "bytes": len(raw)}
    assert json.loads(_read(archive, LEDGER_NAME))["has_accounts"] is True


def test_accounts_file_has_members_with_original_hashes_only(single, tmp_path):
    app, _ = single

    archive = export_with_accounts(app, tmp_path / "备份.zip")

    payload = json.loads(_read(archive, ACCOUNTS_MEMBER))
    rows = {row["username"]: row for row in payload["accounts"]}
    admin = find_account(app, "admin")
    assert set(rows) == {"admin", "alice", "bob"}
    assert rows["admin"]["password_hash"] == admin.password_hash
    assert rows["admin"]["password_hash"].startswith("scrypt$")
    assert (rows["bob"]["role"], rows["alice"]["role"]) == ("admin", "member")
    assert set(rows["alice"]) == {
        "id",
        "username",
        "display_name",
        "role",
        "is_active",
        "source",
        "password_hash",
    }
    assert "is_platform_admin" not in _read(archive, ACCOUNTS_MEMBER).decode()


def test_export_logs_do_not_contain_hashes(single, tmp_path, caplog):
    app, _ = single
    caplog.set_level(logging.DEBUG)

    export_with_accounts(app, tmp_path / "备份.zip")

    assert find_account(app, "admin").password_hash not in caplog.text
    assert "登录账号 3 个" in caplog.text


def test_saas_collects_no_accounts(tmp_path):
    app = make_saas_app(tmp_path)

    assert collect_accounts(app.state.control_session_factory, app.state.settings, "alpha") is None


def test_saas_web_backup_has_no_accounts(tmp_path):
    app = make_saas_app(tmp_path)
    with TestClient(app) as client:
        assert login_at(client, "alpha-admin", slug="alpha").status_code == 200

        job = _web_export(client, headers=host_headers("alpha"))

    archive = ledger_backups_dir(app.state.settings.for_tenant("alpha")) / job["file"]
    manifest = json.loads(_read(archive, MANIFEST_NAME))
    assert _read(archive, ACCOUNTS_MEMBER) is None
    assert all(row["path"] != "accounts.json" for row in manifest["files"])
    assert json.loads(_read(archive, LEDGER_NAME))["has_accounts"] is False
