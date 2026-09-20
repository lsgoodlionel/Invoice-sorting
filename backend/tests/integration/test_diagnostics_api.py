"""诊断接口（设计《日志与故障上报》5.1）：仅管理员可用，默认不上传。"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from invoice_sorting.config import Settings
from invoice_sorting.diagnostics.constants import (
    DIAGNOSTICS_COLLECT_PATH,
    DIAGNOSTICS_STATUS_PATH,
    MSG_UPLOAD_DISABLED,
    REASON_CRASH,
)
from invoice_sorting.main import create_app
from tests.auth_helpers import setup_password
from tests.conftest import make_settings
from tests.diagnostics_helpers import FAKE_REPO, FAKE_TOKEN, FakeTransport, stub_commands


@pytest.fixture
def diag_client(tmp_path: Path, monkeypatch) -> TestClient:
    stub_commands(monkeypatch)
    with TestClient(create_app(make_settings(tmp_path))) as client:
        yield client


def test_status_reports_upload_disabled_by_default(diag_client: TestClient) -> None:
    body = diag_client.get(DIAGNOSTICS_STATUS_PATH).json()

    assert body["ok"]
    assert body["data"]["upload_enabled"] is False
    assert body["data"]["last"] is None


def test_collect_creates_local_package(diag_client: TestClient, tmp_path: Path) -> None:
    # Act
    body = diag_client.post(DIAGNOSTICS_COLLECT_PATH, json={"reason": REASON_CRASH}).json()

    # Assert
    assert body["ok"]
    assert body["data"]["reason"] == REASON_CRASH
    assert body["data"]["package"].startswith("diag_")
    assert not body["data"]["is_uploaded"]


def test_collect_with_upload_but_no_repo_only_keeps_local(diag_client: TestClient) -> None:
    body = diag_client.post(DIAGNOSTICS_COLLECT_PATH, json={"upload": True}).json()

    assert body["data"]["is_uploaded"] is False
    assert body["data"]["message"] == MSG_UPLOAD_DISABLED


def test_status_shows_last_package_after_collect(diag_client: TestClient) -> None:
    diag_client.post(DIAGNOSTICS_COLLECT_PATH, json={})

    last = diag_client.get(DIAGNOSTICS_STATUS_PATH).json()["data"]["last"]

    assert last["package"].startswith("diag_")
    assert last["size"] > 0


def test_invalid_reason_is_rejected(diag_client: TestClient) -> None:
    response = diag_client.post(DIAGNOSTICS_COLLECT_PATH, json={"reason": "随便写"})

    assert response.status_code == 422


def test_upload_goes_to_the_namespaced_repo_path(tmp_path: Path, monkeypatch) -> None:
    # Arrange
    stub_commands(monkeypatch)
    transport = FakeTransport().install(monkeypatch)
    settings = make_settings(tmp_path, log_repo=FAKE_REPO, log_token=FAKE_TOKEN)

    # Act
    with TestClient(create_app(settings)) as client:
        body = client.post(DIAGNOSTICS_COLLECT_PATH, json={"upload": True}).json()

    # Assert
    assert body["data"]["is_uploaded"] is True
    assert transport.sent_paths[0].startswith("invoice-sorting/logs/")
    assert transport.sent_paths[-1] == "invoice-sorting/latest.json"


def test_response_never_contains_the_token(tmp_path: Path, monkeypatch) -> None:
    stub_commands(monkeypatch)
    FakeTransport().install(monkeypatch)
    settings = make_settings(tmp_path, log_repo=FAKE_REPO, log_token=FAKE_TOKEN)

    with TestClient(create_app(settings)) as client:
        status = client.get(DIAGNOSTICS_STATUS_PATH).text
        collected = client.post(DIAGNOSTICS_COLLECT_PATH, json={"upload": True}).text

    assert FAKE_TOKEN not in status
    assert FAKE_TOKEN not in collected


def _auth_client(tmp_path: Path, monkeypatch) -> TestClient:
    stub_commands(monkeypatch)
    return TestClient(create_app(make_settings(tmp_path, auth_enabled=True)))


def test_anonymous_request_is_rejected(tmp_path: Path, monkeypatch) -> None:
    with _auth_client(tmp_path, monkeypatch) as client:
        setup_password(client)
        client.cookies.clear()

        assert client.get(DIAGNOSTICS_STATUS_PATH).status_code == 401
        assert client.post(DIAGNOSTICS_COLLECT_PATH, json={}).status_code == 401


def test_non_admin_gets_403(tmp_path: Path, monkeypatch) -> None:
    # Arrange：管理员建一个普通成员，再以该成员登录
    from tests.auth_helpers import MEMBER_PASSWORD, create_user, login

    with _auth_client(tmp_path, monkeypatch) as client:
        setup_password(client)
        create_user(client, "member1")
        client.cookies.clear()
        assert login(client, MEMBER_PASSWORD, "member1").status_code == 200

        # Act & Assert
        assert client.get(DIAGNOSTICS_STATUS_PATH).status_code == 403
        assert client.post(DIAGNOSTICS_COLLECT_PATH, json={}).status_code == 403


def test_collect_is_allowed_in_readonly_mode(tmp_path: Path, monkeypatch) -> None:
    """只读降级时写请求被拦，但诊断包必须还能生成——这时候最需要它。"""
    from invoice_sorting.licensing.guard import is_write_request

    assert not is_write_request("POST", DIAGNOSTICS_COLLECT_PATH)


def test_settings_defaults_match_the_design(tmp_path: Path) -> None:
    settings: Settings = make_settings(tmp_path)

    assert settings.log_level == "INFO"
    assert settings.log_app == "invoice-sorting"
    assert settings.log_branch == "main"
    assert settings.log_repo == "" and settings.log_token == ""
    assert settings.is_log_upload_configured is False
