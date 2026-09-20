"""授权状态接口与只读降级：写接口 403，查看、导出、备份、登录仍可用。"""

import pytest
from fastapi.testclient import TestClient

from invoice_sorting.licensing.client import VerifyOutcome
from invoice_sorting.licensing.state import (
    STATE_ACTIVE,
    STATE_GRACE,
    STATE_READONLY,
    STATE_UNLICENSED_OK,
)
from invoice_sorting.main import create_app
from tests.conftest import make_settings
from tests.license_helpers import (
    TEST_LICENSE_KEY,
    disable_scheduler,
    install_verifier,
    make_claims,
    sign_claims,
)

STATUS_FIELDS = {
    "state",
    "valid_until",
    "grace_until",
    "max_users",
    "last_checked_at",
    "last_error",
    "server_reachable",
    "message",
    "instance_id",
}
EXPENSE = {"spent_on": "2026-09-15", "amount_cents": 1200, "merchant": "便利店"}


@pytest.fixture
def licensed_app(tmp_path, monkeypatch):
    disable_scheduler(monkeypatch)
    settings = make_settings(
        tmp_path,
        license_key=TEST_LICENSE_KEY,
        license_server="https://license.example.com",
    )
    return create_app(settings)


@pytest.fixture
def licensed_client(licensed_app):
    with TestClient(licensed_app) as client:
        yield client


def read_status(client: TestClient) -> dict:
    response = client.get("/api/license/status")
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_status_reports_all_fields_when_unlicensed(client):
    status = read_status(client)

    assert set(status) == STATUS_FIELDS
    assert status["state"] == STATE_UNLICENSED_OK
    assert status["server_reachable"] is True


def test_unlicensed_instance_can_still_write(client):
    assert client.post("/api/expenses", json=EXPENSE).status_code == 200


def test_fresh_licensed_instance_starts_in_grace(licensed_client):
    status = read_status(licensed_client)

    assert status["state"] == STATE_GRACE
    assert status["grace_until"] is not None
    assert status["instance_id"]


def test_status_never_returns_the_license_key(licensed_client):
    assert TEST_LICENSE_KEY not in licensed_client.get("/api/license/status").text


def test_server_rejection_switches_to_readonly(licensed_app, licensed_client, monkeypatch):
    install_verifier(monkeypatch, VerifyOutcome(is_rejected=True, error="授权密钥无效或已停用"))

    recheck = licensed_client.post("/api/license/recheck")

    assert recheck.status_code == 200, recheck.text
    assert recheck.json()["data"]["state"] == STATE_READONLY
    assert read_status(licensed_client)["state"] == STATE_READONLY


def test_readonly_blocks_writes_but_keeps_reads(licensed_app, licensed_client, monkeypatch):
    install_verifier(monkeypatch, VerifyOutcome(is_rejected=True, error="授权密钥无效或已停用"))
    licensed_client.post("/api/license/recheck")

    blocked = licensed_client.post("/api/expenses", json=EXPENSE)

    assert blocked.status_code == 403
    assert "只读" in blocked.json()["error"]
    assert "联系" in blocked.json()["error"]
    assert licensed_client.get("/api/expenses").status_code == 200
    assert licensed_client.get("/api/settings").status_code == 200


def test_readonly_keeps_backup_and_login_available(licensed_client, monkeypatch):
    install_verifier(monkeypatch, VerifyOutcome(is_rejected=True, error="授权密钥无效或已停用"))
    licensed_client.post("/api/license/recheck")

    assert licensed_client.post("/api/backup").status_code == 200
    assert licensed_client.post("/api/auth/login", json={"password": "x"}).status_code != 403
    assert licensed_client.get("/api/license/status").status_code == 200


def test_successful_verification_restores_write_access(licensed_app, licensed_client, monkeypatch):
    install_verifier(monkeypatch, VerifyOutcome(is_rejected=True, error="授权密钥无效或已停用"))
    licensed_client.post("/api/license/recheck")
    instance_id = licensed_app.state.license_service.instance_id
    token = sign_claims(make_claims(instance_id=instance_id))
    install_verifier(monkeypatch, VerifyOutcome(token=token))

    licensed_app.state.license_service.run_check()

    assert read_status(licensed_client)["state"] == STATE_ACTIVE
    assert licensed_client.post("/api/expenses", json=EXPENSE).status_code == 200


def test_manual_recheck_is_rate_limited(licensed_client, monkeypatch):
    install_verifier(monkeypatch, VerifyOutcome(is_reachable=False, error="无法连接授权服务"))

    assert licensed_client.post("/api/license/recheck").status_code == 200
    assert licensed_client.post("/api/license/recheck").status_code == 429


def test_saas_mode_does_not_expose_local_license_state(saas_client, saas_app, monkeypatch):
    from tests.tenancy_helpers import host_headers, open_tenants

    open_tenants(saas_app, "alpha")

    status = saas_client.get("/api/license/status", headers=host_headers("alpha")).json()["data"]

    assert status["state"] == "not_applicable"


def test_additional_guards_can_block_writes(client):
    """第三批的额度检查通过同一入口接入：注册后立刻对所有写接口生效。"""
    from invoice_sorting.licensing.guard import WriteBlock, register_write_guard

    register_write_guard(
        client.app, lambda conn: WriteBlock(code="quota_exceeded", message="本月新增记录已达上限")
    )

    blocked = client.post("/api/expenses", json=EXPENSE)

    assert blocked.status_code == 403
    assert blocked.json()["error"] == "本月新增记录已达上限"
    assert client.get("/api/expenses").status_code == 200
