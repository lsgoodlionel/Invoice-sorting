"""授权记录：签发（密钥只出现一次）、脱敏展示、吊销、解绑实例与删除。"""

import pytest

from invoice_sorting.licensing.constants import LICENSE_VERIFY_PATH
from tests.license_helpers import test_private_key as signing_key  # noqa: PT028
from tests.platform_helpers import login_platform, platform_app

LICENSES = "/api/platform/licenses"


@pytest.fixture
def app(tmp_path):
    return platform_app(tmp_path)


@pytest.fixture
def client(app):
    return login_platform(app)


def issue(client, **overrides) -> dict:
    body = {"customer_name": "某某学院", "max_users": 30, "note": "年度授权", **overrides}
    response = client.post(LICENSES, json=body)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_issue_returns_the_key_once(client):
    record = issue(client, valid_until="2027-12-31")

    assert record["is_key_visible"] is True
    assert len(record["license_key"]) >= 16
    assert record["customer_name"] == "某某学院" and record["status"] == "active"
    assert record["valid_until"] == "2027-12-31" and record["bound_instance_id"] == ""


def test_list_only_shows_masked_keys(client):
    created = issue(client)

    listed = client.get(LICENSES).json()["data"]

    assert listed[0]["is_key_visible"] is False
    assert "****" in listed[0]["license_key"]
    assert created["license_key"] not in listed[0]["license_key"]


def test_each_key_is_unique(client):
    keys = {issue(client)["license_key"] for _ in range(5)}

    assert len(keys) == 5


def test_revoke_and_restore(client):
    record = issue(client)

    revoked = client.patch(f"{LICENSES}/{record['id']}", json={"status": "revoked"})

    assert revoked.json()["data"]["status"] == "revoked"
    back = client.patch(f"{LICENSES}/{record['id']}", json={"status": "active"})
    assert back.json()["data"]["status"] == "active"


def test_update_customer_and_expiry(client):
    record = issue(client)
    body = {"customer_name": "某某医院", "max_users": 50, "valid_until": None, "note": "永久"}

    data = client.patch(f"{LICENSES}/{record['id']}", json=body).json()["data"]

    assert data["customer_name"] == "某某医院" and data["max_users"] == 50
    assert data["valid_until"] is None and data["note"] == "永久"


def test_unbind_lets_the_customer_move_to_a_new_machine(client, monkeypatch):
    record = issue(client)
    key = record["license_key"]
    _install_signing_key(monkeypatch)
    first = _verify(client, key, "instance-one")
    assert first.status_code == 200, first.text

    assert _verify(client, key, "instance-two").status_code == 403
    assert client.post(f"{LICENSES}/{record['id']}/unbind").status_code == 200
    assert _verify(client, key, "instance-two").status_code == 200


def _install_signing_key(monkeypatch) -> None:
    """用测试私钥替换签发密钥，签发流程不依赖真实部署的密钥文件。"""
    from invoice_sorting.licensing import issuer

    monkeypatch.setattr(issuer, "load_private_key", signing_key)


def _verify(client, key: str, instance_id: str):
    return client.post(LICENSE_VERIFY_PATH, json={"license_key": key, "instance_id": instance_id})


def test_revoked_key_is_rejected_when_verifying(client, monkeypatch):
    record = issue(client)
    _install_signing_key(monkeypatch)
    client.patch(f"{LICENSES}/{record['id']}", json={"status": "revoked"})

    assert _verify(client, record["license_key"], "instance-one").status_code == 403


def test_delete_record(client):
    record = issue(client)

    assert client.delete(f"{LICENSES}/{record['id']}").status_code == 200
    assert client.get(LICENSES).json()["data"] == []


def test_unknown_record_is_404(client):
    assert client.post(f"{LICENSES}/999/unbind").status_code == 404
