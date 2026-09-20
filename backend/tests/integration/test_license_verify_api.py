"""控制面签发接口 /api/platform/license/verify：签名令牌可被客户端验签。"""

from datetime import date, timedelta

import pytest

from invoice_sorting.control.models import LicenseRecord
from invoice_sorting.licensing.keys import ENV_PRIVATE_KEY, load_public_key
from invoice_sorting.licensing.token import decode_token
from tests.license_helpers import TEST_LICENSE_KEY, TEST_PRIVATE_KEY_B64

INSTANCE = "instance-abc"
BODY = {
    "license_key": TEST_LICENSE_KEY,
    "instance_id": INSTANCE,
    "app_version": "0.1.0",
    "users": 3,
    "tenants": 1,
}


@pytest.fixture
def signing_key(monkeypatch):
    monkeypatch.setenv(ENV_PRIVATE_KEY, TEST_PRIVATE_KEY_B64)


def add_record(app, **overrides) -> None:
    values = {
        "license_key": TEST_LICENSE_KEY,
        "customer_name": "某某公司",
        "max_users": 20,
        "valid_until": date.today() + timedelta(days=30),
        "status": "active",
        **overrides,
    }
    with app.state.control_session_factory() as control:
        control.add(LicenseRecord(**values))
        control.commit()


def verify(client, **overrides):
    return client.post("/api/platform/license/verify", json={**BODY, **overrides})


def test_valid_record_returns_token_the_client_can_verify(app, client, signing_key):
    add_record(app)

    response = verify(client)

    assert response.status_code == 200, response.text
    claims = decode_token(response.json()["data"]["token"], load_public_key())
    assert claims.license_key == TEST_LICENSE_KEY
    assert claims.instance_id == INSTANCE
    assert claims.max_users == 20
    assert claims.valid_until is not None
    assert claims.issued_at is not None


def test_unknown_key_is_rejected_without_internal_details(app, client, signing_key):
    response = verify(client, license_key="NOPE-0000")

    assert response.status_code == 403
    assert "无效" in response.json()["error"]
    assert "NOPE-0000" not in response.json()["error"]


def test_suspended_record_is_rejected(app, client, signing_key):
    add_record(app, status="suspended")

    assert verify(client).status_code == 403


def test_expired_record_is_rejected(app, client, signing_key):
    add_record(app, valid_until=date.today() - timedelta(days=1))

    response = verify(client)

    assert response.status_code == 403
    assert "到期" in response.json()["error"]


def test_record_without_expiry_issues_permanent_token(app, client, signing_key):
    add_record(app, valid_until=None)

    claims = decode_token(verify(client).json()["data"]["token"], load_public_key())

    assert claims.valid_until is None


def test_first_instance_is_bound_and_others_are_rejected(app, client, signing_key):
    add_record(app)

    assert verify(client).status_code == 200
    assert verify(client).status_code == 200  # 同一实例可反复校验
    other = verify(client, instance_id="instance-other")

    assert other.status_code == 403
    assert "实例" in other.json()["error"]


def test_binding_and_check_time_are_recorded(app, client, signing_key):
    add_record(app)

    verify(client)

    with app.state.control_session_factory() as control:
        record = control.query(LicenseRecord).one()
        assert record.bound_instance_id == INSTANCE
        assert record.checked_at is not None
        assert record.issued_at is not None


def test_missing_private_key_returns_service_unavailable(app, client, monkeypatch):
    monkeypatch.delenv(ENV_PRIVATE_KEY, raising=False)
    add_record(app)

    response = verify(client)

    assert response.status_code == 503
    assert "授权" in response.json()["error"]


def test_repeated_invalid_keys_are_rate_limited(app, client, signing_key):
    statuses = [verify(client, license_key="NOPE-0000").status_code for _ in range(6)]

    assert statuses[0] == 403
    assert statuses[-1] == 429


def test_verify_endpoint_does_not_require_login(auth_client):
    """未登录也能调用（私有化实例没有控制面账号）。"""
    response = auth_client.post("/api/platform/license/verify", json=BODY)

    assert response.status_code != 401


@pytest.mark.parametrize("body", [{}, {"license_key": ""}, {"instance_id": ""}])
def test_invalid_request_body_is_rejected(app, client, signing_key, body):
    response = client.post("/api/platform/license/verify", json=body)

    assert response.status_code == 422
