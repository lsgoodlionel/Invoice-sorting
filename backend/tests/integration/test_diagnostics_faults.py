"""运行中错误的记录与触发（设计《日志与故障上报》2、5.3）。

用一个只在测试里挂上的路由制造 500，验证：4xx 不进错误日志、5xx 与未捕获异常进日志，
同一指纹累计到阈值才打包。
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from invoice_sorting.common.errors import AppError
from invoice_sorting.diagnostics.constants import REASON_ERROR
from invoice_sorting.diagnostics.service import STATE_SERVICE_KEY
from invoice_sorting.diagnostics.throttle import BURST_THRESHOLD
from invoice_sorting.main import create_app
from tests.conftest import make_settings
from tests.diagnostics_helpers import stub_commands


@pytest.fixture
def faulty_app(tmp_path: Path, monkeypatch):
    stub_commands(monkeypatch)
    app = create_app(make_settings(tmp_path))

    @app.get("/api/测试用崩溃")
    def _boom() -> dict:
        raise ValueError("bad marshal data")

    @app.get("/api/测试用业务错误")
    def _rejected() -> dict:
        raise AppError("这条支出不存在", status_code=404)

    # 后台线程换成同步执行，测试才好断言
    service = getattr(app.state, STATE_SERVICE_KEY)
    service._runner = lambda job: job()
    return app


def _client(app) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def test_unhandled_exception_is_logged_with_method_and_path(faulty_app, caplog) -> None:
    with _client(faulty_app) as client, caplog.at_level("ERROR"):
        response = client.get("/api/测试用崩溃")

    assert response.status_code == 500
    assert "请求处理失败" in caplog.text
    assert "/api/测试用崩溃" in caplog.text


def test_business_error_does_not_enter_the_error_log(faulty_app, caplog) -> None:
    """4xx 是正常的用户操作反馈，不进错误日志，避免噪音。"""
    with _client(faulty_app) as client, caplog.at_level("ERROR"):
        response = client.get("/api/测试用业务错误")

    assert response.status_code == 404
    assert "请求处理失败" not in caplog.text


def test_repeated_faults_trigger_one_package(faulty_app) -> None:
    # Arrange
    service = getattr(faulty_app.state, STATE_SERVICE_KEY)

    # Act
    with _client(faulty_app) as client:
        for _ in range(BURST_THRESHOLD):
            client.get("/api/测试用崩溃")

    # Assert
    assert service.last_report is not None
    assert service.last_report.reason == REASON_ERROR
    assert service.last_report.package.exists()


def test_single_fault_does_not_trigger_a_package(faulty_app) -> None:
    service = getattr(faulty_app.state, STATE_SERVICE_KEY)

    with _client(faulty_app) as client:
        client.get("/api/测试用崩溃")

    assert service.last_report is None


def test_healthy_requests_do_not_touch_diagnostics(faulty_app) -> None:
    service = getattr(faulty_app.state, STATE_SERVICE_KEY)

    with _client(faulty_app) as client:
        assert client.get("/api/health").status_code == 200

    assert service.status()["throttle"]["tracked_fingerprints"] == 0
