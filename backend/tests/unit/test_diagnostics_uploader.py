"""上传到私有日志仓库（设计《日志与故障上报》6 上传）。

这些测试**绝不联网**：唯一发起请求的 `uploader._open` 被 FakeTransport 顶替；
用到的仓库名与令牌都是明显的假值。
"""

import base64
import json
import logging
from pathlib import Path

import pytest

from invoice_sorting.diagnostics.uploader import (
    MSG_REFUSED,
    MSG_TOO_LARGE,
    MSG_UNREACHABLE,
    UploadTarget,
    build_target,
    latest_repo_path,
    package_repo_path,
    update_latest,
    upload_package,
)
from tests.conftest import make_settings
from tests.diagnostics_helpers import (
    FAKE_REPO,
    FAKE_TOKEN,
    FIXED_TIME,
    FakeTransport,
    http_error,
    network_error,
    ok_response,
)

TARGET = UploadTarget(
    repo=FAKE_REPO, token=FAKE_TOKEN, app="invoice-sorting", instance="srv1", branch="main"
)
NO_SLEEP = lambda _seconds: None  # noqa: E731 - 测试里不真的等待


@pytest.fixture
def package(tmp_path: Path) -> Path:
    path = tmp_path / "diag_srv1_20260920-123000_abcd1234.zip"
    path.write_bytes(b"PK fake zip")
    return path


def test_no_target_when_repo_and_token_missing(tmp_path: Path) -> None:
    """默认不上传：没配置就返回 None，调用方据此跳过。"""
    assert build_target(make_settings(tmp_path), "srv1") is None


def test_no_target_when_only_repo_is_configured(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, log_repo=FAKE_REPO)

    assert build_target(settings, "srv1") is None


def test_no_target_when_repo_format_is_invalid(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, log_repo="https://例子", log_token=FAKE_TOKEN)

    assert build_target(settings, "srv1") is None


def test_target_uses_hostname_when_instance_not_configured(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, log_repo=FAKE_REPO, log_token=FAKE_TOKEN)

    target = build_target(settings, "srv-x")

    assert target is not None
    assert target.instance == "srv-x"
    assert target.app == "invoice-sorting"


def test_repo_path_is_namespaced_by_app_instance_and_date() -> None:
    path = package_repo_path(TARGET, FIXED_TIME, "diag_srv1_20260920-123000_abcd1234.zip")

    assert path == "invoice-sorting/logs/srv1/2026-09-20/diag_srv1_20260920-123000_abcd1234.zip"
    assert latest_repo_path(TARGET) == "invoice-sorting/latest.json"


def test_successful_upload_sends_base64_content_to_namespaced_path(monkeypatch, package) -> None:
    # Arrange
    transport = FakeTransport(responses=[ok_response()]).install(monkeypatch)

    # Act
    outcome = upload_package(TARGET, package, FIXED_TIME, "崩溃诊断包", sleep=NO_SLEEP)

    # Assert
    assert outcome.is_uploaded
    assert outcome.repo_path.startswith("invoice-sorting/logs/srv1/2026-09-20/")
    call = transport.calls[0]
    assert call.method == "PUT"
    assert base64.b64decode(call.body["content"]) == b"PK fake zip"
    assert call.body["branch"] == "main"
    assert call.body["message"] == "崩溃诊断包"


def test_token_goes_only_into_the_authorization_header(monkeypatch, package, caplog) -> None:
    transport = FakeTransport(responses=[ok_response()]).install(monkeypatch)

    with caplog.at_level(logging.DEBUG):
        outcome = upload_package(TARGET, package, FIXED_TIME, "诊断包", sleep=NO_SLEEP)

    call = transport.calls[0]
    assert call.headers["authorization"] == f"Bearer {FAKE_TOKEN}"
    assert FAKE_TOKEN not in json.dumps(call.body)
    assert FAKE_TOKEN not in call.url
    assert FAKE_TOKEN not in caplog.text
    assert FAKE_TOKEN not in outcome.error


def test_network_failure_retries_then_reports_unreachable(monkeypatch, package) -> None:
    transport = FakeTransport(responses=[network_error()] * 5).install(monkeypatch)

    outcome = upload_package(TARGET, package, FIXED_TIME, "诊断包", sleep=NO_SLEEP)

    assert not outcome.is_uploaded
    assert outcome.error == MSG_UNREACHABLE
    assert len(transport.calls) == 3  # 首次 + 重试 2 次


def test_network_failure_then_success(monkeypatch, package) -> None:
    FakeTransport(responses=[network_error(), ok_response()]).install(monkeypatch)

    outcome = upload_package(TARGET, package, FIXED_TIME, "诊断包", sleep=NO_SLEEP)

    assert outcome.is_uploaded


def test_permission_error_is_not_retried(monkeypatch, package) -> None:
    body = json.dumps({"message": "Resource not accessible by personal access token"})
    transport = FakeTransport(responses=[http_error(403, body)]).install(monkeypatch)

    outcome = upload_package(TARGET, package, FIXED_TIME, "诊断包", sleep=NO_SLEEP)

    assert not outcome.is_uploaded
    assert MSG_REFUSED in outcome.error
    assert "personal access token" in outcome.error
    assert len(transport.calls) == 1


def test_empty_repository_first_upload_retries_without_branch(monkeypatch, package) -> None:
    """lsgoodlionel/paper 目前没有任何提交：带 branch 会 404，去掉 branch 由 GitHub 建默认分支。"""
    # Arrange
    refusal = http_error(404, json.dumps({"message": "Branch main not found"}))
    transport = FakeTransport(responses=[refusal, ok_response()]).install(monkeypatch)

    # Act
    outcome = upload_package(TARGET, package, FIXED_TIME, "诊断包", sleep=NO_SLEEP)

    # Assert
    assert outcome.is_uploaded
    assert len(transport.calls) == 2
    assert "branch" in transport.calls[0].body
    assert "branch" not in transport.calls[1].body


def test_empty_repository_retry_failure_reports_clear_reason(monkeypatch, package) -> None:
    body = json.dumps({"message": "Not Found"})
    FakeTransport(responses=[http_error(404, body), http_error(404, body)]).install(monkeypatch)

    outcome = upload_package(TARGET, package, FIXED_TIME, "诊断包", sleep=NO_SLEEP)

    assert not outcome.is_uploaded
    assert "HTTP 404" in outcome.error
    assert "Not Found" in outcome.error


def test_oversized_package_is_not_sent(monkeypatch, tmp_path: Path) -> None:
    transport = FakeTransport().install(monkeypatch)
    huge = tmp_path / "diag_big.zip"
    huge.write_bytes(b"0" * (6 * 1024 * 1024))

    outcome = upload_package(TARGET, huge, FIXED_TIME, "诊断包", sleep=NO_SLEEP)

    assert outcome.error == MSG_TOO_LARGE
    assert transport.calls == []


def test_latest_json_is_updated_with_existing_sha(monkeypatch) -> None:
    # Arrange：先 GET 现有 sha，再带 sha PUT 覆盖
    transport = FakeTransport(responses=[ok_response({"sha": "old-sha"}), ok_response()]).install(
        monkeypatch
    )
    payload = {"fingerprint": "abcd1234", "package": "invoice-sorting/logs/srv1/x.zip"}

    # Act
    outcome = update_latest(TARGET, payload, "更新 latest", sleep=NO_SLEEP)

    # Assert
    assert outcome.is_uploaded
    assert outcome.repo_path == "invoice-sorting/latest.json"
    assert transport.calls[0].method == "GET"
    assert transport.calls[1].body["sha"] == "old-sha"
    assert json.loads(base64.b64decode(transport.calls[1].body["content"]))["fingerprint"] == (
        "abcd1234"
    )


def test_latest_json_is_created_when_absent(monkeypatch) -> None:
    transport = FakeTransport(
        responses=[http_error(404, json.dumps({"message": "Not Found"})), ok_response()]
    ).install(monkeypatch)

    outcome = update_latest(TARGET, {"fingerprint": "abcd1234"}, "创建 latest", sleep=NO_SLEEP)

    assert outcome.is_uploaded
    assert "sha" not in transport.calls[1].body


def test_missing_package_file_is_reported(monkeypatch, tmp_path: Path) -> None:
    FakeTransport().install(monkeypatch)

    outcome = upload_package(TARGET, tmp_path / "不存在.zip", FIXED_TIME, "诊断包", sleep=NO_SLEEP)

    assert not outcome.is_uploaded
    assert outcome.error
