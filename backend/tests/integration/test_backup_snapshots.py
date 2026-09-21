"""数据库快照：列出与下载本账本快照；控制库备份与越界路径一律拒绝。"""

import pytest

SNAPSHOTS = "/api/backup/snapshots"


def test_manual_backup_appears_in_list_and_downloads(client, settings):
    created = client.post("/api/backup").json()["data"]

    items = client.get(SNAPSHOTS).json()["data"]

    assert [item["name"] for item in items] == [created["name"]]
    assert items[0]["kind"] == "manual" and items[0]["size"] > 0
    response = client.get(f"{SNAPSHOTS}/{created['name']}")
    assert response.status_code == 200
    assert response.content[:16] == b"SQLite format 3\x00"


def test_upgrade_backups_are_listed_but_control_backups_never(client, settings):
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    (settings.backup_dir / "upgrade_20260920_090842.db").write_bytes(b"x")
    (settings.backup_dir / "control_upgrade_20260920_090842.db").write_bytes(b"secret")
    (settings.backup_dir / "notes.txt").write_text("x", encoding="utf-8")

    items = client.get(SNAPSHOTS).json()["data"]

    assert [(item["name"], item["kind"]) for item in items] == [
        ("upgrade_20260920_090842.db", "upgrade")
    ]
    assert client.get(f"{SNAPSHOTS}/control_upgrade_20260920_090842.db").status_code == 404


@pytest.mark.parametrize(
    "name",
    [
        "..%2Finvoice.db",
        "invoice.db",
        "invoice_1.db%2F..%2F..%2Fcontrol.db",
        "control.db",
        "invoice_x.db",
    ],
)
def test_download_rejects_anything_outside_the_whitelist(client, settings, name):
    assert client.get(f"{SNAPSHOTS}/{name}").status_code == 404


def test_snapshots_require_admin(admin_client, auth_app):
    from tests.auth_helpers import create_user, logged_in_client

    create_user(admin_client, "member1")
    member = logged_in_client(auth_app, "member1")

    assert member.get(SNAPSHOTS).status_code == 403
    assert admin_client.get(SNAPSHOTS).status_code == 200
