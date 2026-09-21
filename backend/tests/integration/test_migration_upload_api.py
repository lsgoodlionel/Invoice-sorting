"""网页导入 · 分片上传协议：登记、乱序与重传、缺片、校验和、体积上限、过期清理与取消。"""

import os

import pytest

from invoice_sorting.main import create_app
from invoice_sorting.migration.upload_store import MAX_PACKAGE_BYTES
from tests.import_helpers import (
    IMPORTS,
    PART,
    age_session,
    build_package,
    complete,
    create_upload,
    put_part,
    session_dir,
    split,
    upload_all,
)


@pytest.fixture
def package(app, session, settings, tmp_path) -> bytes:
    data = build_package(app, session, settings, tmp_path)
    assert len(data) > PART, "测试包至少要能切成两片"
    return data


def test_create_returns_upload_id_and_part_layout(client, package):
    created = create_upload(client, package)

    assert len(created["upload_id"]) == 32
    assert created["part_size"] == PART
    assert created["part_count"] == len(split(package))
    assert created["status"] == "uploading"
    assert created["missing_parts"] == list(range(created["part_count"]))


def test_parts_out_of_order_and_retransmitted_still_complete(client, package):
    upload_id = create_upload(client, package)["upload_id"]
    parts = split(package)

    for index in reversed(range(len(parts))):
        assert put_part(client, upload_id, index, parts[index]).status_code == 200
    # 第 0 片先传一份坏的，再重传正确内容覆盖
    assert put_part(client, upload_id, 0, b"\x00" * len(parts[0])).status_code == 200
    assert put_part(client, upload_id, 0, parts[0]).status_code == 200
    response = complete(client, upload_id)

    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "ready"


def test_status_reports_received_and_missing_parts(client, package):
    upload_id = create_upload(client, package)["upload_id"]
    put_part(client, upload_id, 1, split(package)[1])

    data = client.get(f"{IMPORTS}/{upload_id}/status").json()["data"]

    assert data["received_parts"] == [1]
    assert 0 in data["missing_parts"] and 1 not in data["missing_parts"]


def test_missing_part_is_rejected_on_complete(client, package):
    upload_id = create_upload(client, package)["upload_id"]
    put_part(client, upload_id, 0, split(package)[0])

    response = complete(client, upload_id)

    assert response.status_code == 400
    assert "缺少分片" in response.json()["error"]


@pytest.mark.parametrize("index", [-1, 99])
def test_part_index_out_of_range(client, package, index):
    upload_id = create_upload(client, package)["upload_id"]

    response = put_part(client, upload_id, index, b"x")

    assert response.status_code in (400, 404, 422)


def test_part_with_wrong_size_is_rejected(client, package):
    upload_id = create_upload(client, package)["upload_id"]

    short = put_part(client, upload_id, 0, split(package)[0][:-1])
    long = put_part(client, upload_id, 0, split(package)[0] + b"x")

    assert short.status_code == 400 and "分片大小" in short.json()["error"]
    assert long.status_code == 400
    assert client.get(f"{IMPORTS}/{upload_id}/status").json()["data"]["received_parts"] == []


def test_whole_package_hash_mismatch_is_rejected(client, package):
    upload_id = create_upload(client, package, sha256="0" * 64)["upload_id"]
    upload_all(client, upload_id, package)

    response = complete(client, upload_id)
    status = client.get(f"{IMPORTS}/{upload_id}/status").json()["data"]

    assert response.status_code == 400
    assert "校验和不符" in response.json()["error"]
    assert status["status"] == "failed"


def test_non_zip_payload_is_rejected(client):
    junk = os.urandom(PART + 10)
    upload_id = create_upload(client, junk)["upload_id"]
    upload_all(client, upload_id, junk)

    response = complete(client, upload_id)

    assert response.status_code == 400
    assert "zip" in response.json()["error"]


def test_oversized_package_is_rejected_with_cli_hint(client):
    response = client.post(
        IMPORTS,
        json={"filename": "巨型.zip", "size": MAX_PACKAGE_BYTES + 1, "sha256": "a" * 64},
    )

    assert response.status_code == 400
    assert "2 GB" in response.json()["error"] and "命令行" in response.json()["error"]


def test_default_part_size_is_eight_megabytes(client):
    response = client.post(IMPORTS, json={"filename": "a.zip", "size": 100, "sha256": "a" * 64})

    assert response.json()["data"]["part_size"] == 8 * 1024 * 1024


def test_invalid_part_size_is_rejected(client):
    response = client.post(
        IMPORTS, json={"filename": "a.zip", "size": 100, "part_size": 10, "sha256": "a" * 64}
    )

    assert response.status_code == 400
    assert "分片大小" in response.json()["error"]


def test_upload_after_complete_is_conflict(client, package):
    upload_id = create_upload(client, package)["upload_id"]
    upload_all(client, upload_id, package)
    complete(client, upload_id)

    response = put_part(client, upload_id, 0, split(package)[0])

    assert response.status_code == 409


def test_merged_package_replaces_parts_on_disk(client, package, settings):
    upload_id = create_upload(client, package)["upload_id"]
    upload_all(client, upload_id, package)
    complete(client, upload_id)

    directory = session_dir(settings, upload_id)

    assert (directory / "package.zip").read_bytes() == package
    assert not any((directory / "parts").glob("*"))


def test_cancel_deletes_files(client, package, settings):
    upload_id = create_upload(client, package)["upload_id"]
    put_part(client, upload_id, 0, split(package)[0])

    response = client.delete(f"{IMPORTS}/{upload_id}")

    assert response.status_code == 200
    assert not session_dir(settings, upload_id).exists()
    assert client.get(f"{IMPORTS}/{upload_id}/status").status_code == 404


def test_expired_sessions_are_swept_when_a_new_one_starts(client, package, settings):
    stale = create_upload(client, package)["upload_id"]
    fresh = create_upload(client, package)["upload_id"]
    age_session(settings, stale, hours=25)

    create_upload(client, package)

    assert not session_dir(settings, stale).exists()
    assert session_dir(settings, fresh).exists()


def test_expired_sessions_are_swept_on_startup(client, package, settings):
    stale = create_upload(client, package)["upload_id"]
    age_session(settings, stale, hours=25)

    create_app(settings)

    assert not session_dir(settings, stale).exists()


def test_unknown_or_malformed_upload_id_is_not_found(client):
    assert client.get(f"{IMPORTS}/{'0' * 32}/status").status_code == 404
    assert client.get(f"{IMPORTS}/..%2F..%2Fetc/status").status_code == 404
