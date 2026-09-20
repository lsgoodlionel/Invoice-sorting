"""授权校验的网络客户端：超时、重试上限、4xx 与 5xx 的区别。"""

import io
import json
import urllib.error

import pytest

from invoice_sorting.licensing import client as license_client
from invoice_sorting.licensing.client import (
    MAX_ATTEMPTS,
    VerifyRequest,
    verify_with_server,
)

SERVER = "https://license.example.com"
REQUEST = VerifyRequest(
    license_key="TEST-LICENSE-0001",
    instance_id="instance-1",
    app_version="0.1.0",
    users=3,
    tenants=1,
)


class _Response(io.BytesIO):
    """urlopen 返回的上下文管理器替身。"""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False


def _envelope(data: dict) -> _Response:
    return _Response(json.dumps({"ok": True, "data": data, "error": None}).encode())


def _http_error(status: int, message: str) -> urllib.error.HTTPError:
    body = json.dumps({"ok": False, "data": None, "error": message}).encode()
    return urllib.error.HTTPError(SERVER, status, message, {}, io.BytesIO(body))


def test_successful_verification_returns_token(monkeypatch):
    seen: list[dict] = []

    def fake_open(request, timeout):
        seen.append(json.loads(request.data))
        return _envelope({"token": "payload.signature"})

    monkeypatch.setattr(license_client, "_open", fake_open)

    outcome = verify_with_server(SERVER, REQUEST)

    assert outcome.token == "payload.signature"
    assert outcome.is_reachable is True
    assert outcome.is_rejected is False
    assert seen[0]["license_key"] == "TEST-LICENSE-0001"
    assert seen[0]["instance_id"] == "instance-1"
    assert seen[0]["users"] == 3


def test_client_error_means_license_rejected(monkeypatch):
    attempts: list[int] = []

    def fake_open(request, timeout):
        attempts.append(1)
        raise _http_error(403, "授权密钥无效或已停用")

    monkeypatch.setattr(license_client, "_open", fake_open)

    outcome = verify_with_server(SERVER, REQUEST, sleep=lambda _: None)

    assert outcome.is_rejected is True
    assert outcome.is_reachable is True
    assert "无效" in outcome.error
    assert len(attempts) == 1  # 明确判定不重试


def test_server_error_is_treated_as_unreachable_and_retried(monkeypatch):
    attempts: list[int] = []

    def fake_open(request, timeout):
        attempts.append(1)
        raise _http_error(500, "boom")

    monkeypatch.setattr(license_client, "_open", fake_open)

    outcome = verify_with_server(SERVER, REQUEST, sleep=lambda _: None)

    assert outcome.is_reachable is False
    assert outcome.is_rejected is False
    assert len(attempts) == MAX_ATTEMPTS


def test_network_failure_is_unreachable(monkeypatch):
    def fake_open(request, timeout):
        raise urllib.error.URLError("name resolution failed")

    monkeypatch.setattr(license_client, "_open", fake_open)

    outcome = verify_with_server(SERVER, REQUEST, sleep=lambda _: None)

    assert outcome.is_reachable is False
    assert outcome.token == ""


def test_broken_response_body_is_unreachable(monkeypatch):
    monkeypatch.setattr(license_client, "_open", lambda request, timeout: _Response(b"not json"))

    outcome = verify_with_server(SERVER, REQUEST, sleep=lambda _: None)

    assert outcome.is_reachable is False


def test_non_http_server_address_is_refused(monkeypatch):
    def fail(request, timeout):  # pragma: no cover - 不应被调用
        raise AssertionError("不应发起请求")

    monkeypatch.setattr(license_client, "_open", fail)

    outcome = verify_with_server("file:///etc/passwd", REQUEST)

    assert outcome.is_reachable is False
    assert outcome.is_rejected is False


def test_license_key_never_appears_in_logs(monkeypatch, caplog):
    monkeypatch.setattr(
        license_client, "_open", lambda request, timeout: _envelope({"token": "a.b"})
    )

    with caplog.at_level("DEBUG"):
        verify_with_server(SERVER, REQUEST)

    assert "TEST-LICENSE-0001" not in caplog.text


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_all_client_errors_are_rejections(monkeypatch, status):
    monkeypatch.setattr(
        license_client,
        "_open",
        lambda request, timeout: (_ for _ in ()).throw(_http_error(status, "无效")),
    )

    assert verify_with_server(SERVER, REQUEST, sleep=lambda _: None).is_rejected is True
