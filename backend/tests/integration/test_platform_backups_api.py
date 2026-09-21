"""平台数据库（control.db）备份：仅 SaaS、仅平台管理员、保留份数、白名单下载、单账套 404。"""

import sqlite3
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from invoice_sorting.platform_admin.backups import (
    KEEP_PLATFORM_BACKUPS,
    platform_backups_dir,
)
from tests.platform_helpers import login_platform, platform_app
from tests.tenancy_helpers import host_headers, login_at

BACKUPS = "/api/platform/backups"
SQLITE_MAGIC = b"SQLite format 3\x00"


@pytest.fixture
def ops_app(tmp_path):
    return platform_app(tmp_path)


@pytest.fixture
def ops(ops_app) -> TestClient:
    return login_platform(ops_app)


def _create(client) -> dict:
    response = client.post(BACKUPS)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_platform_admin_creates_lists_and_downloads(ops_app, ops, tmp_path):
    created = _create(ops)

    listed = ops.get(BACKUPS).json()["data"]
    download = ops.get(f"{BACKUPS}/{created['name']}")

    assert created["name"].startswith("control_") and created["size"] > 0
    assert "secret.key" in created["notice"] and "密码哈希" in created["notice"]
    assert [item["name"] for item in listed["items"]] == [created["name"]]
    assert "INVOICE_SORTING_SECRET_KEY" in listed["notice"]
    assert download.status_code == 200 and download.content.startswith(SQLITE_MAGIC)
    copy = tmp_path / "下载的控制库.db"
    copy.write_bytes(download.content)
    with closing(sqlite3.connect(copy)) as conn:
        usernames = {row[0] for row in conn.execute("select username from account")}
    assert {"alpha-admin", "beta-admin", "ops-admin"} <= usernames


def test_backups_live_under_platform_root_not_in_any_tenant(ops_app, ops):
    created = _create(ops)

    directory = platform_backups_dir(ops_app.state.settings)

    assert (directory / created["name"]).is_file()
    assert directory == ops_app.state.settings.data_dir / "备份" / "平台"
    assert "tenants" not in directory.parts


def test_retention_keeps_latest_ten(ops_app, ops):
    for _ in range(KEEP_PLATFORM_BACKUPS + 2):
        _create(ops)

    items = ops.get(BACKUPS).json()["data"]["items"]

    assert len(items) == KEEP_PLATFORM_BACKUPS
    assert len(list(platform_backups_dir(ops_app.state.settings).glob("*.db"))) == 10


def test_tenant_admin_is_forbidden(ops_app, ops):
    created = _create(ops)
    tenant_admin = TestClient(ops_app)
    assert login_at(tenant_admin, "alpha-admin", slug="alpha").status_code == 200
    headers = host_headers("alpha")

    assert tenant_admin.post(BACKUPS, headers=headers).status_code == 403
    assert tenant_admin.get(BACKUPS, headers=headers).status_code == 403
    download = tenant_admin.get(f"{BACKUPS}/{created['name']}", headers=headers)
    assert download.status_code == 403


@pytest.mark.parametrize(
    "name",
    [
        "control.db",
        "..%2Fcontrol.db",
        "control_20260101_000000.db",  # 形状合法但不存在
        "control_upgrade_20260101_000000.db",
        "invoice_20260101_000000.db",
    ],
)
def test_download_rejects_names_outside_whitelist(ops_app, ops, name):
    _create(ops)
    root = ops_app.state.settings.backup_dir
    (root / "control_upgrade_20260101_000000.db").write_bytes(b"x")

    assert ops.get(f"{BACKUPS}/{name}").status_code == 404


def test_single_tenant_deployment_has_no_platform_backups(client):
    """单账套没有独立的平台：管理员访问也是 404（账号随控制库，不在账本备份里）。"""
    assert client.post(BACKUPS).status_code == 404
    assert client.get(BACKUPS).status_code == 404
    assert client.get(f"{BACKUPS}/control_20260101_000000.db").status_code == 404
