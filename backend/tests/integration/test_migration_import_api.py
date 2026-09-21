"""网页导入 · 预览与执行：权限、账套隔离、覆盖确认、只读守卫与完整流程。"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from invoice_sorting.config import DEFAULT_TENANT_NAME
from invoice_sorting.control.models import TENANT_STATUS_SUSPENDED
from invoice_sorting.db.models import Expense
from invoice_sorting.licensing.guard import WriteBlock, register_write_guard
from invoice_sorting.migration import engine_bridge as engine
from tests.auth_helpers import create_user, logged_in_client
from tests.import_helpers import (
    IMPORTS,
    build_package,
    complete,
    create_upload,
    put_part,
    split,
    upload_all,
    uploaded,
)
from tests.migration_helpers import SAMPLE_EXPENSES
from tests.platform_helpers import login_platform, platform_app
from tests.quota_helpers import update_tenant
from tests.tenancy_helpers import host_headers, login_at, open_tenants

EXPORT = "/api/backup/export-tenant"
READONLY = "系统只读（测试）"
EXTRA_EXPENSE = {"spent_on": "2026-09-20", "amount_cents": 100, "merchant": "虚构多出来的店"}
SMALL_BODY = {"filename": "a.zip", "size": 10, "sha256": "a" * 64}


@pytest.fixture
def package(app, session, settings, tmp_path) -> bytes:
    return build_package(app, session, settings, tmp_path)


def _confirm(client, upload_id: str, headers=None, **body):
    return client.post(f"{IMPORTS}/{upload_id}/confirm", json=body, headers=headers)


def _status(client, upload_id: str, headers=None) -> dict:
    response = client.get(f"{IMPORTS}/{upload_id}/status", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _expense_count(app) -> int:
    with app.state.tenants.get("default").session_factory() as db:
        return len(list(db.scalars(select(Expense))))


def _fake_engine(calls: list) -> SimpleNamespace:
    report = {"source": {"tenant": "虚构来源"}, "items": [{"key": "expenses", "added": 3}]}

    def preview_import(runtime, control_factory, archive_path, slug, mode, include_settings=True):
        calls.append(("preview", slug, mode, archive_path.is_file(), include_settings))
        return report

    def run_import(runtime, control_factory, archive_path, slug, mode, include_settings=True):
        calls.append(("run", slug, mode, archive_path.is_file(), include_settings))
        return {**report, "warnings": ["虚构提示"]}

    return SimpleNamespace(preview_import=preview_import, run_import=run_import)


def test_full_replace_flow_restores_package_contents(app, client, package, settings):
    """创建 → 上传两片 → 完成（预览）→ 确认覆盖 → 状态 done，数据回到包里的样子。"""
    created = client.post("/api/expenses", json={**EXTRA_EXPENSE})
    assert created.status_code == 200, created.text
    assert _expense_count(app) == len(SAMPLE_EXPENSES) + 1
    upload_id = create_upload(client, package)["upload_id"]
    assert len(split(package)) >= 2
    upload_all(client, upload_id, package)

    preview = complete(client, upload_id).json()["data"]
    confirmed = _confirm(client, upload_id, mode="replace", confirm_name=DEFAULT_TENANT_NAME)
    final = _status(client, upload_id)

    assert preview["status"] == "ready" and preview["target_name"] == DEFAULT_TENANT_NAME
    assert "items" in preview
    assert confirmed.status_code == 200, confirmed.text
    assert final["status"] == "done", final["error"]
    assert final["backup_file"].startswith("覆盖前备份_")
    assert (settings.backup_dir / final["backup_file"]).is_file()
    assert _expense_count(app) == len(SAMPLE_EXPENSES)


def test_package_files_are_removed_after_import(client, package, settings):
    from tests.import_helpers import session_dir

    upload_id = uploaded(client, package)
    _confirm(client, upload_id, mode="replace", confirm_name=DEFAULT_TENANT_NAME)

    assert not (session_dir(settings, upload_id) / "package.zip").exists()
    assert _status(client, upload_id)["status"] == "done"


def test_replace_requires_matching_confirm_name(client, package):
    upload_id = uploaded(client, package)

    missing = _confirm(client, upload_id, mode="replace")
    wrong = _confirm(client, upload_id, mode="replace", confirm_name="别的账套")

    assert missing.status_code == 400 and DEFAULT_TENANT_NAME in missing.json()["error"]
    assert wrong.status_code == 400
    assert _status(client, upload_id)["status"] == "ready"


def test_confirm_before_complete_is_conflict(client, package):
    upload_id = create_upload(client, package)["upload_id"]

    response = _confirm(client, upload_id, mode="merge")

    assert response.status_code == 409


def test_merge_uses_engine_preview_and_run(client, package, monkeypatch):
    calls: list = []
    monkeypatch.setattr(engine, "load_engine", lambda: _fake_engine(calls))
    upload_id = uploaded(client, package)

    confirmed = _confirm(client, upload_id, mode="merge")
    final = _status(client, upload_id)

    assert calls == [
        ("preview", "default", "merge", True, True),
        ("run", "default", "merge", True, True),
    ]
    assert confirmed.status_code == 200
    assert final["status"] == "done" and final["mode"] == "merge"
    assert final["report"]["items"] == [{"key": "expenses", "added": 3}]
    assert final["report"]["warnings"] == ["虚构提示"]


def test_include_settings_flag_reaches_engine(client, package, monkeypatch):
    calls: list = []
    monkeypatch.setattr(engine, "load_engine", lambda: _fake_engine(calls))
    upload_id = create_upload(client, package)["upload_id"]
    upload_all(client, upload_id, package)

    previewed = complete(client, upload_id, mode="merge", include_settings=False)
    _confirm(client, upload_id, mode="merge", include_settings=False)
    final = _status(client, upload_id)

    assert previewed.json()["data"]["include_settings"] is False
    assert [call[-1] for call in calls] == [False, False]
    assert final["include_settings"] is False


def test_include_settings_must_be_boolean(client, package):
    upload_id = create_upload(client, package)["upload_id"]
    upload_all(client, upload_id, package)

    response = complete(client, upload_id, include_settings="yes")

    assert response.status_code == 422


def test_complete_can_repreview_in_another_mode(client, package, monkeypatch):
    calls: list = []
    monkeypatch.setattr(engine, "load_engine", lambda: _fake_engine(calls))
    upload_id = uploaded(client, package)

    again = complete(client, upload_id, mode="replace")

    assert again.status_code == 200
    assert calls[-1][:3] == ("preview", "default", "replace")


def test_engine_failure_marks_job_failed(client, package, monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError("虚构故障")

    fake = SimpleNamespace(preview_import=lambda *a, **k: {"items": []}, run_import=broken)
    monkeypatch.setattr(engine, "load_engine", lambda: fake)
    upload_id = uploaded(client, package)

    _confirm(client, upload_id, mode="merge")
    final = _status(client, upload_id)

    assert final["status"] == "failed"
    assert "导入失败" in final["error"] and "虚构故障" not in final["error"]


def test_without_engine_merge_is_refused_but_replace_works(client, package, monkeypatch):
    monkeypatch.setattr(engine, "load_engine", lambda: None)
    upload_id = uploaded(client, package)

    merge = _confirm(client, upload_id, mode="merge")
    replace = _confirm(client, upload_id, mode="replace", confirm_name=DEFAULT_TENANT_NAME)

    assert merge.status_code == 400 and "合并导入" in merge.json()["error"]
    assert replace.status_code == 200
    assert _status(client, upload_id)["status"] == "done"


def test_import_requires_admin(auth_app, admin_client):
    create_user(admin_client, "member9")
    member = logged_in_client(auth_app, "member9")
    body = SMALL_BODY

    assert member.post(IMPORTS, json=body).status_code == 403
    assert admin_client.post(IMPORTS, json=body).status_code == 200


def test_readonly_blocks_import_but_not_export(client, package):
    upload_id = create_upload(client, package)["upload_id"]
    register_write_guard(client.app, lambda conn: WriteBlock(code="readonly", message=READONLY))

    created = client.post(IMPORTS, json=SMALL_BODY)
    part = put_part(client, upload_id, 0, split(package)[0])
    exported = client.post(EXPORT, json={"include_packages": False})

    assert created.status_code == 403 and created.json()["error"] == READONLY
    assert part.status_code == 403
    assert exported.status_code == 200, exported.text
    assert client.get(f"{EXPORT}/{exported.json()['data']['job']}/status").status_code == 200
    assert client.get(f"{IMPORTS}/{upload_id}/status").status_code == 200


def test_suspended_saas_tenant_can_export_but_not_import(saas_app, saas_client):
    open_tenants(saas_app, "alpha")
    headers = host_headers("alpha")
    saas_client.get("/api/expenses", headers=headers)
    update_tenant(saas_app, "alpha", status=TENANT_STATUS_SUSPENDED)
    body = SMALL_BODY

    blocked = saas_client.post(IMPORTS, json=body, headers=headers)
    exported = saas_client.post(EXPORT, headers=headers)

    assert blocked.status_code == 403 and "账套已停用" in blocked.json()["error"]
    assert exported.status_code == 200, exported.text


def test_saas_sessions_are_isolated_per_tenant(saas_app, saas_client, saas_settings):
    open_tenants(saas_app, "alpha", "beta")
    alpha, beta = host_headers("alpha"), host_headers("beta")
    data = b"\x01" * 100
    upload_id = create_upload(saas_client, data, headers=alpha)["upload_id"]

    peek = saas_client.get(f"{IMPORTS}/{upload_id}/status", headers=beta)
    write = put_part(saas_client, upload_id, 0, data, headers=beta)
    cancel = saas_client.delete(f"{IMPORTS}/{upload_id}", headers=beta)

    assert (peek.status_code, write.status_code, cancel.status_code) == (404, 404, 404)
    assert _status(saas_client, upload_id, headers=alpha)["status"] == "uploading"
    assert saas_settings.for_tenant("alpha").data_dir in _session_parents(saas_settings, upload_id)


def _session_parents(settings, upload_id: str) -> list:
    from invoice_sorting.migration.upload_store import STAGING_DIRNAME

    return [
        path.parent.parent.parent
        for path in settings.data_dir.rglob(f"{STAGING_DIRNAME}/{upload_id}/session.json")
    ]


def test_client_cannot_name_another_tenant(saas_app, saas_client):
    open_tenants(saas_app, "alpha", "beta")
    body = {**SMALL_BODY, "slug": "beta"}

    response = saas_client.post(IMPORTS, json=body, headers=host_headers("alpha"))

    assert response.status_code == 422


def test_tenant_admin_cannot_use_platform_import(tmp_path):
    app = platform_app(tmp_path)
    admin = TestClient(app)
    assert login_at(admin, "alpha-admin", slug="alpha").status_code == 200

    response = admin.post(
        "/api/platform/tenants/beta/imports", json=SMALL_BODY, headers=host_headers("alpha")
    )

    assert response.status_code == 403


def test_platform_admin_can_import_into_any_tenant(tmp_path):
    app = platform_app(tmp_path)
    platform = login_platform(app)
    base = "/api/platform/tenants/beta/imports"
    data = b"\x02" * 100

    created = create_upload(platform, data, base=base)
    assert put_part(platform, created["upload_id"], 0, data, base=base).status_code == 200
    status = platform.get(f"{base}/{created['upload_id']}/status").json()["data"]
    unknown = platform.post("/api/platform/tenants/nobody/imports", json=SMALL_BODY)

    assert created["slug"] == "beta"
    assert status["received_parts"] == [0]
    assert unknown.status_code == 404


def test_export_job_reports_include_packages_flag(client, package):
    job = client.post(EXPORT, json={"include_packages": False}).json()["data"]

    assert job["include_packages"] is False
