"""授权令牌：Ed25519 验签、绑定校验与防重放。"""

import base64
import json
from datetime import timedelta

import pytest

from invoice_sorting.db.models import now
from invoice_sorting.licensing.keys import load_public_key
from invoice_sorting.licensing.token import (
    LicenseTokenError,
    decode_token,
    verify_claims,
)
from tests.license_helpers import TEST_LICENSE_KEY, make_claims, make_token, sign_claims

INSTANCE = "instance-1"


def test_signed_token_can_be_verified_with_builtin_public_key():
    raw = make_token(max_users=7)

    claims = decode_token(raw, load_public_key())

    assert claims.license_key == TEST_LICENSE_KEY
    assert claims.instance_id == INSTANCE
    assert claims.max_users == 7
    assert claims.valid_until is not None


def test_tampered_payload_is_rejected():
    raw = make_token(max_users=1)
    payload_b64, signature = raw.split(".")
    payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
    forged = {**payload, "max_users": 999}
    forged_b64 = (
        base64.urlsafe_b64encode(json.dumps(forged, sort_keys=True).encode()).decode().rstrip("=")
    )

    with pytest.raises(LicenseTokenError):
        decode_token(f"{forged_b64}.{signature}", load_public_key())


@pytest.mark.parametrize("raw", ["", "abc", "a.b.c", "!!!.???"])
def test_malformed_token_is_rejected(raw):
    with pytest.raises(LicenseTokenError):
        decode_token(raw, load_public_key())


def test_token_for_another_license_key_is_rejected():
    claims = make_claims(license_key="OTHER-KEY")

    with pytest.raises(LicenseTokenError):
        verify_claims(claims, TEST_LICENSE_KEY, INSTANCE, now(), None)


def test_token_for_another_instance_is_rejected():
    claims = make_claims(instance_id="instance-9")

    with pytest.raises(LicenseTokenError):
        verify_claims(claims, TEST_LICENSE_KEY, INSTANCE, now(), None)


def test_replayed_old_token_is_rejected():
    moment = now()
    claims = make_claims(issued_at=moment - timedelta(days=3))

    with pytest.raises(LicenseTokenError):
        verify_claims(claims, TEST_LICENSE_KEY, INSTANCE, moment, None)


def test_token_issued_in_the_far_future_is_rejected():
    moment = now()
    claims = make_claims(issued_at=moment + timedelta(hours=3))

    with pytest.raises(LicenseTokenError):
        verify_claims(claims, TEST_LICENSE_KEY, INSTANCE, moment, None)


def test_token_older_than_stored_one_is_rejected():
    moment = now()
    previous = moment - timedelta(minutes=5)
    claims = make_claims(issued_at=moment - timedelta(minutes=30))

    with pytest.raises(LicenseTokenError):
        verify_claims(claims, TEST_LICENSE_KEY, INSTANCE, moment, previous)


def test_fresh_token_passes_all_checks():
    moment = now()
    claims = make_claims(issued_at=moment)

    verify_claims(claims, TEST_LICENSE_KEY, INSTANCE, moment, moment - timedelta(days=1))


def test_signature_of_other_key_is_rejected():
    """用另一把私钥签名的令牌无法通过内置公钥验签。"""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from invoice_sorting.licensing.token import encode_token

    raw = encode_token(make_claims(), Ed25519PrivateKey.generate())

    with pytest.raises(LicenseTokenError):
        decode_token(raw, load_public_key())


def test_permanent_token_has_no_valid_until():
    raw = sign_claims(make_claims(days_valid=None))

    assert decode_token(raw, load_public_key()).valid_until is None
