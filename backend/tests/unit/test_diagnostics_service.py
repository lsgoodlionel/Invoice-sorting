"""诊断服务编排：触发、限流、上传与拒绝上传（设计《日志与故障上报》5、6）。"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from invoice_sorting.diagnostics import collect as collect_module
from invoice_sorting.diagnostics.constants import (
    MSG_UPLOAD_DISABLED,
    MSG_UPLOAD_OK,
    REASON_ERROR,
    REASON_MANUAL,
)
from invoice_sorting.diagnostics.service import DiagnosticsService
from invoice_sorting.diagnostics.throttle import BURST_THRESHOLD, DAILY_TOTAL
from tests.conftest import make_settings
from tests.diagnostics_helpers import (
    FAKE_REPO,
    FAKE_TOKEN,
    FIXED_TIME,
    FakeTransport,
    http_error,
    network_error,
    ok_response,
    stub_commands,
)


def _raise_bad_marshal() -> None:
    raise ValueError("bad marshal data")


def _captured() -> BaseException:
    try:
        _raise_bad_marshal()
    except ValueError as error:
        return error
    raise AssertionError  # pragma: no cover


class _Clock:
    """可控时钟，避免测试依赖真实时间。"""

    def __init__(self) -> None:
        self.moment = FIXED_TIME

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, **kwargs) -> None:
        self.moment = self.moment + timedelta(**kwargs)


def _service(tmp_path: Path, monkeypatch, **overrides) -> DiagnosticsService:
    stub_commands(monkeypatch)
    settings = make_settings(tmp_path, **overrides)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    settings.log_file.write_text("启动完成\n", encoding="utf-8")
    return DiagnosticsService(settings, runner=lambda job: job(), clock=_Clock())


def _uploading_service(tmp_path: Path, monkeypatch) -> DiagnosticsService:
    return _service(tmp_path, monkeypatch, log_repo=FAKE_REPO, log_token=FAKE_TOKEN)


def test_manual_collect_without_upload_keeps_package_local(tmp_path, monkeypatch) -> None:
    service = _service(tmp_path, monkeypatch)

    report = service.collect(REASON_MANUAL, upload=False)

    assert report.package.exists()
    assert not report.is_uploaded
    assert report.reason == REASON_MANUAL


def test_upload_is_skipped_when_repo_is_not_configured(tmp_path, monkeypatch) -> None:
    """默认不上传：即使显式要求上传，没配置也只留在本机。"""
    transport = FakeTransport().install(monkeypatch)
    service = _service(tmp_path, monkeypatch)

    report = service.collect(REASON_MANUAL, upload=True)

    assert not report.is_uploaded
    assert report.message == MSG_UPLOAD_DISABLED
    assert transport.calls == []


def test_upload_sends_package_then_updates_latest(tmp_path, monkeypatch) -> None:
    # Arrange：zip 的 PUT、latest.json 的 GET 与 PUT
    transport = FakeTransport(
        responses=[ok_response(), http_error(404, "{}"), ok_response()]
    ).install(monkeypatch)
    service = _uploading_service(tmp_path, monkeypatch)

    # Act
    report = service.collect(REASON_MANUAL, upload=True)

    # Assert
    assert report.is_uploaded
    assert report.message == MSG_UPLOAD_OK
    assert report.repo_path.startswith("invoice-sorting/logs/")
    assert transport.sent_paths[-1] == "invoice-sorting/latest.json"


def test_latest_json_records_fingerprint_and_package_path(tmp_path, monkeypatch) -> None:
    import base64

    transport = FakeTransport(
        responses=[ok_response(), http_error(404, "{}"), ok_response()]
    ).install(monkeypatch)
    service = _uploading_service(tmp_path, monkeypatch)

    service.collect(REASON_MANUAL, upload=True)

    latest = json.loads(base64.b64decode(transport.calls[-1].body["content"]))
    assert latest["app"] == "invoice-sorting"
    assert latest["package"].startswith("invoice-sorting/logs/")
    assert "time" in latest and "version" in latest


def test_failed_upload_keeps_local_package_and_reports_reason(tmp_path, monkeypatch) -> None:
    FakeTransport(responses=[network_error()] * 5).install(monkeypatch)
    service = _uploading_service(tmp_path, monkeypatch)

    report = service.collect(REASON_MANUAL, upload=True)

    assert not report.is_uploaded
    assert report.package.exists()
    assert "无法连接日志仓库" in report.message


def test_residue_self_check_blocks_upload(tmp_path, monkeypatch, caplog) -> None:
    # Arrange：让脱敏失效，日志里的邮箱会留在包内
    monkeypatch.setattr(collect_module, "redact_mapping", lambda parts: dict(parts))
    transport = FakeTransport().install(monkeypatch)
    service = _uploading_service(tmp_path, monkeypatch)
    service._settings.log_file.write_text("用户 li@example-corp.cn 登录", encoding="utf-8")

    # Act
    report = service.collect(REASON_MANUAL, upload=True)

    # Assert
    assert not report.is_uploaded
    assert "邮箱" in report.message
    assert transport.calls == []
    assert report.package.exists()  # 本机包仍然保留，供人工核对


def test_fault_triggers_collection_after_threshold(tmp_path, monkeypatch) -> None:
    service = _service(tmp_path, monkeypatch)

    for _ in range(BURST_THRESHOLD - 1):
        service.record_fault(_captured())
    assert service.last_report is None

    service.record_fault(_captured())
    assert service.last_report is not None
    assert service.last_report.reason == REASON_ERROR


def test_same_fault_is_collected_once_per_day(tmp_path, monkeypatch) -> None:
    service = _service(tmp_path, monkeypatch)
    for _ in range(BURST_THRESHOLD):
        service.record_fault(_captured())
    first = service.last_report

    for _ in range(BURST_THRESHOLD * 2):
        service.record_fault(_captured())

    assert service.last_report is first


def test_throttle_state_survives_service_restart(tmp_path, monkeypatch) -> None:
    """崩溃重启循环：新进程读回落盘的计数，不会每次重启都重新上报。"""
    service = _service(tmp_path, monkeypatch)
    for _ in range(BURST_THRESHOLD):
        service.record_fault(_captured())

    restarted = DiagnosticsService(service._settings, runner=lambda job: job(), clock=_Clock())
    for _ in range(BURST_THRESHOLD):
        restarted.record_fault(_captured())

    assert restarted.last_report is None


def test_status_reports_upload_switch_and_throttle(tmp_path, monkeypatch) -> None:
    service = _service(tmp_path, monkeypatch)

    before = service.status()
    for _ in range(BURST_THRESHOLD):
        service.record_fault(_captured())
    after = service.status()

    assert before["upload_enabled"] is False
    assert before["repo"] == ""
    assert before["last"] is None
    assert after["throttle"]["daily_used"] == 1
    assert after["throttle"]["daily_remaining"] == DAILY_TOTAL - 1
    assert after["last"]["reason"] == REASON_ERROR


def test_status_hides_repo_when_upload_disabled(tmp_path, monkeypatch) -> None:
    """未启用上传时不回显仓库配置，避免界面误导。"""
    service = _service(tmp_path, monkeypatch, log_repo=FAKE_REPO)

    assert service.status()["repo"] == ""


def test_status_never_contains_the_token(tmp_path, monkeypatch) -> None:
    service = _uploading_service(tmp_path, monkeypatch)

    assert FAKE_TOKEN not in json.dumps(service.status(), ensure_ascii=False)


def test_collect_failure_is_swallowed_by_collect_safely(tmp_path, monkeypatch) -> None:
    service = _service(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "invoice_sorting.diagnostics.service.collect_package",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("磁盘满")),
    )

    assert service.collect_safely(REASON_MANUAL, upload=False) is None


def test_record_fault_never_raises_when_tracker_fails(tmp_path, monkeypatch) -> None:
    service = _service(tmp_path, monkeypatch)
    monkeypatch.setattr(
        service._tracker, "record", lambda *a: (_ for _ in ()).throw(OSError("磁盘满"))
    )

    fault = service.record_fault(_captured())

    assert fault.exc_type == "ValueError"


def test_health_provider_failure_does_not_block_package(tmp_path, monkeypatch) -> None:
    stub_commands(monkeypatch)
    settings = make_settings(tmp_path)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    service = DiagnosticsService(
        settings,
        health_provider=lambda: (_ for _ in ()).throw(RuntimeError("授权服务未就绪")),
        runner=lambda job: job(),
        clock=_Clock(),
    )

    assert service.collect(REASON_MANUAL, upload=False).package.exists()


def test_concurrent_collect_is_rejected(tmp_path, monkeypatch) -> None:
    """崩溃风暴下只允许一个打包在跑，不会堆出一堆线程。"""
    service = _service(tmp_path, monkeypatch)
    service._busy.acquire()

    with pytest.raises(RuntimeError):
        service.collect(REASON_MANUAL, upload=False)
