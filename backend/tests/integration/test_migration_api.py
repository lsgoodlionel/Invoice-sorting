"""搬迁接口：后台任务 + 状态查询 + 下载，平台侧与私有化侧各一套，权限沿用管理员校验。"""

import zipfile

import pytest

from invoice_sorting.migration.jobs import KEEP_EXPORTS, exports_dir
from tests.auth_helpers import create_user, logged_in_client
from tests.migration_helpers import seed_tenant_data
from tests.tenancy_helpers import host_headers, open_tenants

TENANT_EXPORT = "/api/backup/export-tenant"
PLATFORM_EXPORT = "/api/platform/tenants/default/export"


@pytest.fixture
def seeded_client(client, settings, session, tmp_path):
    seed_tenant_data(session, settings, tmp_path / "来源")
    return client


def _start(client, url: str = TENANT_EXPORT, **kwargs) -> dict:
    """POST 只登记任务并立即返回（状态为 running），打包在后台进行。"""
    response = client.post(url, **kwargs)
    assert response.status_code == 200, response.text
    job = response.json()["data"]
    assert job["status"] == "running"
    return job


def _finished(client, job: dict, **kwargs) -> dict:
    """查询任务状态直到拿到结果；后台任务在下一次请求前已完成。"""
    response = client.get(f"{job['download_url']}/status", **kwargs)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "done", data["error"]
    return data


def test_tenant_export_returns_finished_job(seeded_client, settings):
    job = _finished(seeded_client, _start(seeded_client))

    assert job["slug"] == "default"
    assert job["file_count"] > 0 and job["size"] > 0
    assert (exports_dir(settings) / job["file"]).is_file()


def test_tenant_export_status_and_download(seeded_client):
    job = _start(seeded_client)

    status = seeded_client.get(f"{TENANT_EXPORT}/{job['job']}/status")
    downloaded = seeded_client.get(job["download_url"])

    assert status.json()["data"]["status"] == "done"
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == "application/zip"
    assert downloaded.content[:2] == b"PK"


def test_downloaded_package_is_importable(seeded_client, tmp_path):
    job = _start(seeded_client)
    saved = tmp_path / "下载包.zip"
    saved.write_bytes(seeded_client.get(job["download_url"]).content)

    with zipfile.ZipFile(saved) as package:
        names = package.namelist()

    assert "manifest.json" in names
    assert "data/invoice.db" in names


def test_export_without_packages(seeded_client, settings):
    job = _finished(seeded_client, _start(seeded_client, json={"include_packages": False}))

    with zipfile.ZipFile(exports_dir(settings) / job["file"]) as package:
        names = package.namelist()

    assert not any(name.startswith("data/资料包/") for name in names)


def test_old_packages_are_pruned(seeded_client, settings):
    for _ in range(KEEP_EXPORTS + 2):
        _start(seeded_client)

    assert len(list(exports_dir(settings).glob("*.zip"))) == KEEP_EXPORTS


def test_unknown_job_is_not_found(seeded_client):
    response = seeded_client.get(f"{TENANT_EXPORT}/0123456789abcdef/status")

    assert response.status_code == 404


def test_platform_export_for_known_tenant(seeded_client, settings):
    job = _finished(seeded_client, _start(seeded_client, url=PLATFORM_EXPORT))

    assert job["download_url"].startswith("/api/platform/tenants/default/export/")
    assert (exports_dir(settings) / job["file"]).is_file()
    assert seeded_client.get(job["download_url"]).status_code == 200


def test_platform_export_rejects_unknown_and_invalid_slug(seeded_client):
    unknown = seeded_client.post("/api/platform/tenants/nobody/export")
    invalid = seeded_client.post("/api/platform/tenants/BAD_SLUG/export")

    assert unknown.status_code == 404
    assert invalid.status_code == 400
    assert "账套标识" in invalid.json()["error"]


def test_platform_export_in_saas_mode(saas_app, saas_client):
    open_tenants(saas_app, "alpha")
    headers = host_headers("alpha")
    saas_client.post(
        "/api/expenses", json={"spent_on": "2026-09-15", "amount_cents": 900}, headers=headers
    )

    response = saas_client.post("/api/platform/tenants/alpha/export", headers=headers)
    job = _finished(saas_client, response.json()["data"], headers=headers)

    assert response.status_code == 200, response.text
    assert job["slug"] == "alpha"
    assert saas_client.get(job["download_url"], headers=headers).status_code == 200


def test_export_requires_admin(auth_app, admin_client):
    create_user(admin_client, "member9")
    member = logged_in_client(auth_app, "member9")

    assert member.post(TENANT_EXPORT).status_code == 403
    assert member.post(PLATFORM_EXPORT).status_code == 403
    assert admin_client.post(TENANT_EXPORT).status_code == 200
