"""授权状态机：有效、宽限、只读，以及“网络不可达”与“服务器判定无效”的区别。"""

from datetime import timedelta

from invoice_sorting.config import Settings
from invoice_sorting.db.models import now
from invoice_sorting.licensing.state import (
    STATE_ACTIVE,
    STATE_GRACE,
    STATE_NOT_APPLICABLE,
    STATE_READONLY,
    STATE_UNLICENSED_OK,
    LicenseSnapshot,
    resolve_status,
)

GRACE_DAYS = 14


def licensed_settings(**overrides) -> Settings:
    values = {
        "license_key": "TEST-LICENSE-0001",
        "license_server": "https://license.example.com",
        "license_grace_days": GRACE_DAYS,
        **overrides,
    }
    return Settings(**values)


def snapshot(moment, valid_until, **overrides) -> LicenseSnapshot:
    values = {
        "instance_id": "instance-1",
        "created_at": moment - timedelta(days=100),
        "valid_until": valid_until,
        "issued_at": moment - timedelta(hours=1),
        "checked_at": moment - timedelta(hours=1),
        "max_users": 5,
        **overrides,
    }
    return LicenseSnapshot(**values)


def test_unconfigured_single_tenant_is_unlicensed_ok():
    moment = now()
    status = resolve_status(Settings(), snapshot(moment, moment), moment)

    assert status.state == STATE_UNLICENSED_OK
    assert status.is_readonly is False


def test_saas_mode_does_not_use_local_license():
    moment = now()
    settings = licensed_settings(deployment_mode="saas")

    status = resolve_status(settings, snapshot(moment, moment - timedelta(days=90)), moment)

    assert status.state == STATE_NOT_APPLICABLE
    assert status.is_readonly is False


def test_valid_token_is_active():
    moment = now()
    valid_until = moment + timedelta(days=5)

    status = resolve_status(licensed_settings(), snapshot(moment, valid_until), moment)

    assert status.state == STATE_ACTIVE
    assert status.valid_until == valid_until
    assert status.grace_until == valid_until + timedelta(days=GRACE_DAYS)
    assert status.max_users == 5


def test_permanent_token_never_expires():
    moment = now()

    status = resolve_status(licensed_settings(), snapshot(moment, None), moment)

    assert status.state == STATE_ACTIVE
    assert status.grace_until is None


def test_expired_token_enters_grace():
    moment = now()
    valid_until = moment - timedelta(days=2)

    status = resolve_status(licensed_settings(), snapshot(moment, valid_until), moment)

    assert status.state == STATE_GRACE
    assert status.is_readonly is False
    assert status.grace_until == valid_until + timedelta(days=GRACE_DAYS)


def test_grace_period_end_turns_readonly():
    moment = now()
    valid_until = moment - timedelta(days=GRACE_DAYS + 1)

    status = resolve_status(licensed_settings(), snapshot(moment, valid_until), moment)

    assert status.state == STATE_READONLY
    assert status.is_readonly is True
    assert "只读" in status.message


def test_server_rejection_turns_readonly_immediately():
    moment = now()
    valid_until = moment + timedelta(days=100)

    status = resolve_status(
        licensed_settings(), snapshot(moment, valid_until, is_revoked=True), moment
    )

    assert status.state == STATE_READONLY
    assert "联系" in status.message


def test_unreachable_server_does_not_downgrade_valid_license():
    moment = now()
    unreachable = snapshot(
        moment,
        moment + timedelta(days=3),
        server_reachable=False,
        last_error="无法连接授权服务",
    )

    status = resolve_status(licensed_settings(), unreachable, moment)

    assert status.state == STATE_ACTIVE
    assert status.server_reachable is False
    assert status.last_error == "无法连接授权服务"


def test_unreachable_server_keeps_grace_after_expiry():
    moment = now()
    unreachable = snapshot(
        moment, moment - timedelta(days=3), server_reachable=False, last_error="超时"
    )

    status = resolve_status(licensed_settings(), unreachable, moment)

    assert status.state == STATE_GRACE


def test_fresh_install_without_token_starts_grace_from_install_time():
    moment = now()
    fresh = LicenseSnapshot(instance_id="instance-1", created_at=moment - timedelta(days=1))

    status = resolve_status(licensed_settings(), fresh, moment)

    assert status.state == STATE_GRACE
    assert status.grace_until == fresh.created_at + timedelta(days=GRACE_DAYS)


def test_fresh_install_turns_readonly_after_grace_without_any_token():
    moment = now()
    fresh = LicenseSnapshot(
        instance_id="instance-1", created_at=moment - timedelta(days=GRACE_DAYS + 1)
    )

    status = resolve_status(licensed_settings(), fresh, moment)

    assert status.state == STATE_READONLY


def test_missing_server_address_is_unlicensed_ok():
    moment = now()
    settings = licensed_settings(license_server="")

    assert resolve_status(settings, snapshot(moment, moment), moment).state == STATE_UNLICENSED_OK
