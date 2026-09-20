"""授权服务：校验结果落库、状态推导、手动复检限流与 instance_id 持久化。"""

from datetime import timedelta

import pytest

from invoice_sorting.common.errors import AppError
from invoice_sorting.config import Settings
from invoice_sorting.control.database import (
    create_control_engine,
    init_control_db,
    make_control_session_factory,
)
from invoice_sorting.db.models import now
from invoice_sorting.licensing.client import VerifyOutcome
from invoice_sorting.licensing.service import LicenseService
from invoice_sorting.licensing.state import STATE_ACTIVE, STATE_GRACE, STATE_READONLY
from invoice_sorting.licensing.storage import read_or_create_instance_id
from tests.license_helpers import TEST_LICENSE_KEY, make_claims, sign_claims


@pytest.fixture
def control_factory(tmp_path):
    settings = Settings(data_dir=tmp_path / "data")
    engine = create_control_engine(settings)
    init_control_db(engine)
    try:
        yield make_control_session_factory(engine)
    finally:
        engine.dispose()


def make_settings(tmp_path, **overrides) -> Settings:
    values = {
        "data_dir": tmp_path / "data",
        "license_key": TEST_LICENSE_KEY,
        "license_server": "https://license.example.com",
        "license_grace_days": 14,
        **overrides,
    }
    return Settings(**values)


class Responder:
    """可在构造服务之后替换返回值的假校验器。"""

    def __init__(self, outcome: VerifyOutcome | None = None) -> None:
        self.outcome = outcome or VerifyOutcome(is_reachable=False, error="超时")
        self.requests: list = []

    def __call__(self, server: str, request) -> VerifyOutcome:
        self.requests.append(request)
        return self.outcome


def build_service(tmp_path, control_factory, verifier, **overrides) -> LicenseService:
    service = LicenseService(
        make_settings(tmp_path, **overrides), control_factory, verifier=verifier
    )
    service.start()
    return service


def token_for(service: LicenseService, **kwargs) -> str:
    return sign_claims(make_claims(instance_id=service.instance_id, **kwargs))


def test_instance_id_is_generated_once_and_reused(tmp_path):
    settings = make_settings(tmp_path)
    first = read_or_create_instance_id(settings)
    second = read_or_create_instance_id(settings)

    assert first == second
    assert len(first) == 36


def test_successful_check_stores_token_and_turns_active(tmp_path, control_factory):
    responder = Responder()
    service = build_service(tmp_path, control_factory, responder)
    responder.outcome = VerifyOutcome(token=token_for(service))

    status = service.run_check()

    assert status.state == STATE_ACTIVE
    assert status.server_reachable is True
    assert status.last_checked_at is not None
    assert status.max_users == 5


def test_stored_token_survives_restart(tmp_path, control_factory):
    responder = Responder()
    service = build_service(tmp_path, control_factory, responder)
    responder.outcome = VerifyOutcome(token=token_for(service))
    service.run_check()

    restarted = build_service(tmp_path, control_factory, Responder())

    assert restarted.status().state == STATE_ACTIVE
    assert restarted.instance_id == service.instance_id


def test_server_rejection_turns_readonly(tmp_path, control_factory):
    service = build_service(
        tmp_path,
        control_factory,
        lambda server, request: VerifyOutcome(is_rejected=True, error="授权密钥无效或已停用"),
    )

    status = service.run_check()

    assert status.state == STATE_READONLY
    assert "无效" in status.last_error


def test_unreachable_server_keeps_previous_token(tmp_path, control_factory):
    responder = Responder()
    service = build_service(tmp_path, control_factory, responder)
    responder.outcome = VerifyOutcome(token=token_for(service))
    service.run_check()

    responder.outcome = VerifyOutcome(is_reachable=False, error="无法连接授权服务")
    status = service.run_check()

    assert status.state == STATE_ACTIVE
    assert status.server_reachable is False
    assert status.last_error == "无法连接授权服务"


def test_expired_token_and_unreachable_server_stay_in_grace(tmp_path, control_factory):
    responder = Responder()
    service = build_service(tmp_path, control_factory, responder)
    responder.outcome = VerifyOutcome(token=token_for(service, days_valid=-1))
    service.run_check()

    responder.outcome = VerifyOutcome(is_reachable=False, error="超时")

    assert service.run_check().state == STATE_GRACE


def test_token_with_bad_signature_does_not_downgrade(tmp_path, control_factory):
    service = build_service(
        tmp_path, control_factory, lambda server, request: VerifyOutcome(token="bad.token")
    )

    status = service.run_check()

    assert status.state == STATE_GRACE  # 全新实例仍在宽限期内，不因验签失败立即只读
    assert status.last_error != ""


def test_token_bound_to_another_instance_is_refused(tmp_path, control_factory):
    service = build_service(
        tmp_path,
        control_factory,
        lambda server, request: VerifyOutcome(token=sign_claims(make_claims(instance_id="other"))),
    )

    status = service.run_check()

    assert status.state == STATE_GRACE
    assert status.last_checked_at is None


def test_replayed_token_is_refused(tmp_path, control_factory):
    responder = Responder()
    service = build_service(tmp_path, control_factory, responder)
    responder.outcome = VerifyOutcome(token=token_for(service))
    service.run_check()

    stale = token_for(service, issued_at=now() - timedelta(hours=6))
    responder.outcome = VerifyOutcome(token=stale)
    status = service.run_check()

    assert status.last_error != ""
    assert status.state == STATE_ACTIVE  # 仍使用此前的有效令牌


def test_manual_recheck_is_rate_limited(tmp_path, control_factory):
    clicks = iter([100.0, 110.0, 400.0])
    service = LicenseService(
        make_settings(tmp_path),
        control_factory,
        verifier=lambda server, request: VerifyOutcome(is_reachable=False, error="超时"),
        monotonic=lambda: next(clicks),
    )
    service.start()

    service.recheck()
    with pytest.raises(AppError) as excinfo:
        service.recheck()

    assert excinfo.value.status_code == 429
    service.recheck()


def test_disabled_service_never_calls_the_server(tmp_path, control_factory):
    def fail(server, request):  # pragma: no cover - 不应被调用
        raise AssertionError("未配置授权时不应联网")

    service = build_service(tmp_path, control_factory, fail, license_key="")

    assert service.is_enabled is False
    assert service.run_check().is_readonly is False


def test_request_reports_users_and_tenants(tmp_path, control_factory):
    responder = Responder()
    service = build_service(tmp_path, control_factory, responder)
    service.run_check()

    assert responder.requests[0].instance_id == service.instance_id
    assert responder.requests[0].users >= 0
    assert responder.requests[0].app_version != ""
