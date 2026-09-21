"""账本备份包（备份即导出）：按账套存放、列表与下载、跨账套隔离、白名单、只读可用、保留份数。"""

import json
import os

import pytest
from fastapi.testclient import TestClient

from invoice_sorting.licensing.guard import WriteBlock, register_write_guard
from invoice_sorting.migration.jobs import exports_dir
from invoice_sorting.migration.ledger_backups import KEEP_LEDGER_BACKUPS, ledger_backups_dir
from tests.migration_helpers import seed_tenant_data
from tests.platform_helpers import make_saas_app
from tests.tenancy_helpers import add_member, host_headers, login_at

EXPORT = "/api/backup/export-tenant"
PACKAGES = "/api/backup/packages"
READONLY = "系统只读（虚构测试原因）"


@pytest.fixture
def seeded_client(client, settings, session, tmp_path):
    seed_tenant_data(session, settings, tmp_path / "来源")
    return client


def _export(client, headers=None, **body) -> dict:
    response = client.post(EXPORT, json=body or None, headers=headers)
    assert response.status_code == 200, response.text
    job = response.json()["data"]
    status = client.get(f"{job['download_url']}/status", headers=headers).json()["data"]
    assert status["status"] == "done", status["error"]
    return status


def _list(client, headers=None) -> list[dict]:
    response = client.get(PACKAGES, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_export_lands_in_tenant_backup_dir_and_is_listed(seeded_client, settings):
    job = _export(seeded_client, include_packages=False)

    packages = _list(seeded_client)

    directory = settings.backup_dir / "账本备份"
    assert ledger_backups_dir(settings) == directory
    assert (directory / job["file"]).is_file()
    assert not exports_dir(settings).exists()
    assert [item["name"] for item in packages] == [job["file"]]
    item = packages[0]
    assert item["size"] == job["size"] and item["created_at"]
    assert item["include_packages"] is False and item["file_count"] == job["file_count"]


def test_list_is_newest_first(seeded_client, settings):
    first = _export(seeded_client)["file"]
    second = _export(seeded_client)["file"]
    older = ledger_backups_dir(settings) / first
    stamp = older.stat().st_mtime - 60
    os.utime(older, (stamp, stamp))

    names = [item["name"] for item in _list(seeded_client)]

    assert names == [second, first]


def test_download_returns_the_same_zip(seeded_client, settings):
    job = _export(seeded_client)

    response = seeded_client.get(f"{PACKAGES}/{job['file']}")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.content == (ledger_backups_dir(settings) / job["file"]).read_bytes()


def test_list_survives_broken_sidecar(seeded_client, settings):
    job = _export(seeded_client)
    sidecar = ledger_backups_dir(settings) / f"{job['file']}.json"
    sidecar.write_text("{不是 JSON", encoding="utf-8")

    item = _list(seeded_client)[0]

    assert item["name"] == job["file"] and item["include_packages"] is True


@pytest.mark.parametrize(
    "name",
    [
        "..%2F..%2Fcontrol.db",
        "notes.txt",
        "control_20260101_000000.db",
        "invoice_20260101_000000.db",
        "账套_default_20260101_000000.zip",  # 形状合法但不存在
        "账套_default_20260101_000000.zip.json",
        "账套_DEFAULT_20260101_000000.zip",
    ],
)
def test_download_rejects_names_outside_whitelist(seeded_client, settings, name):
    backup_root = settings.backup_dir
    backup_root.mkdir(parents=True, exist_ok=True)
    (backup_root / "notes.txt").write_text("虚构", encoding="utf-8")
    (backup_root / "control_20260101_000000.db").write_bytes(b"secret")

    assert seeded_client.get(f"{PACKAGES}/{name}").status_code == 404


def test_file_outside_backup_dir_with_valid_name_is_not_served(seeded_client, settings):
    """白名单形状的文件放在别的目录（例如平台导出区）也拿不到。"""
    stray = exports_dir(settings) / "账套_default_20260101_000000.zip"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_bytes(b"PK")

    assert seeded_client.get(f"{PACKAGES}/{stray.name}").status_code == 404
    assert _list(seeded_client) == []


def test_readonly_still_allows_export_list_and_download(seeded_client, app):
    register_write_guard(app, lambda _conn: WriteBlock(code="readonly", message=READONLY))
    assert seeded_client.post("/api/categories", json={"name": "虚构"}).status_code == 403

    job = _export(seeded_client)

    assert [item["name"] for item in _list(seeded_client)] == [job["file"]]
    assert seeded_client.get(f"{PACKAGES}/{job['file']}").status_code == 200


def test_retention_keeps_latest_ten_with_sidecars(seeded_client, settings):
    for _ in range(KEEP_LEDGER_BACKUPS + 2):
        _export(seeded_client)

    directory = ledger_backups_dir(settings)
    assert len(_list(seeded_client)) == KEEP_LEDGER_BACKUPS
    assert len(list(directory.glob("*.zip.json"))) == KEEP_LEDGER_BACKUPS


# ---- SaaS：按账套隔离 ----


@pytest.fixture
def saas(tmp_path):
    app = make_saas_app(tmp_path)
    with TestClient(app) as base:
        yield app, base


def _tenant_client(app, slug: str) -> TestClient:
    client = TestClient(app)
    response = login_at(client, f"{slug}-admin", slug=slug)
    assert response.status_code == 200, response.text
    return client


def test_saas_backups_are_isolated_per_tenant(saas):
    app, _ = saas
    alpha, beta = _tenant_client(app, "alpha"), _tenant_client(app, "beta")
    alpha_headers, beta_headers = host_headers("alpha"), host_headers("beta")

    job = _export(alpha, headers=alpha_headers)

    alpha_dir = ledger_backups_dir(app.state.settings.for_tenant("alpha"))
    assert (alpha_dir / job["file"]).is_file()
    assert "tenants" in alpha_dir.parts and "alpha" in alpha_dir.parts
    assert [item["name"] for item in _list(alpha, alpha_headers)] == [job["file"]]
    assert _list(beta, beta_headers) == []
    assert beta.get(f"{PACKAGES}/{job['file']}", headers=beta_headers).status_code == 404
    assert alpha.get(f"{PACKAGES}/{job['file']}", headers=alpha_headers).status_code == 200


def test_saas_retention_is_counted_per_tenant(saas):
    app, _ = saas
    alpha, beta = _tenant_client(app, "alpha"), _tenant_client(app, "beta")
    beta_job = _export(beta, headers=host_headers("beta"))

    for _ in range(KEEP_LEDGER_BACKUPS + 1):
        _export(alpha, headers=host_headers("alpha"))

    assert len(_list(alpha, host_headers("alpha"))) == KEEP_LEDGER_BACKUPS
    assert [item["name"] for item in _list(beta, host_headers("beta"))] == [beta_job["file"]]


def test_member_cannot_list_or_download(saas):
    app, _ = saas
    add_member(app, "alpha", "alpha-member")
    admin = _tenant_client(app, "alpha")
    job = _export(admin, headers=host_headers("alpha"))
    member = TestClient(app)
    login_at(member, "alpha-member", slug="alpha")

    assert member.get(PACKAGES, headers=host_headers("alpha")).status_code == 403
    download = member.get(f"{PACKAGES}/{job['file']}", headers=host_headers("alpha"))
    assert download.status_code == 403


def test_sidecar_has_no_paths(seeded_client, settings):
    job = _export(seeded_client)

    meta = json.loads(
        (ledger_backups_dir(settings) / f"{job['file']}.json").read_text(encoding="utf-8")
    )

    assert set(meta) == {"include_packages", "file_count", "exported_by"}
