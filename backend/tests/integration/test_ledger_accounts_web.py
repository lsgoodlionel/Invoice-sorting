"""网页导入与登录账号：覆盖预览的 accounts 分区、执行后本人需用备份密码重新登录、篡改被拒。

测试数据全部虚构。
"""

import zipfile

import pytest
from fastapi.testclient import TestClient

from invoice_sorting.config import DEFAULT_TENANT_NAME
from tests.accounts_helpers import (
    ACCOUNTS_MEMBER,
    NEW_ADMIN_PASSWORD,
    OLD_ADMIN_PASSWORD,
    export_with_accounts,
    machine,
    prepare_new_machine,
    prepare_old_machine,
)
from tests.auth_helpers import login
from tests.import_helpers import IMPORTS, complete, create_upload, upload_all
from tests.migration_helpers import seed_tenant_data


@pytest.fixture
def backup(tmp_path):
    app = machine(tmp_path / "旧机器")
    with TestClient(app) as client:
        prepare_old_machine(client)
    with app.state.tenants.get("default").session_factory() as db:
        seed_tenant_data(db, app.state.settings, tmp_path / "来源")
    return export_with_accounts(app, tmp_path / "备份.zip")


@pytest.fixture
def admin(tmp_path):
    app = machine(tmp_path / "新机器")
    with TestClient(app) as client:
        prepare_new_machine(client)
        yield client


def _upload(client, data: bytes) -> str:
    upload_id = create_upload(client, data)["upload_id"]
    upload_all(client, upload_id, data)
    return upload_id


def test_replace_preview_has_accounts_section_and_warning(admin, backup):
    upload_id = _upload(admin, backup.read_bytes())

    merge = complete(admin, upload_id).json()["data"]
    replace = complete(admin, upload_id, mode="replace").json()["data"]

    assert merge["accounts"]["will_restore"] is False
    assert "合并模式不导入账号" in merge["accounts"]["note"]
    assert replace["accounts"]["will_restore"] is True
    assert "需用备份时的密码重新登录" in replace["accounts"]["note"]
    assert any(item["key"] == "accounts" for item in replace["items"])


def test_confirmed_replace_signs_admin_out_until_backup_password(admin, backup):
    upload_id = _upload(admin, backup.read_bytes())
    complete(admin, upload_id, mode="replace")

    confirmed = admin.post(
        f"{IMPORTS}/{upload_id}/confirm",
        json={"mode": "replace", "confirm_name": DEFAULT_TENANT_NAME},
    )

    assert confirmed.status_code == 200, confirmed.text
    assert admin.get(f"{IMPORTS}/{upload_id}/status").status_code == 401
    assert login(admin, NEW_ADMIN_PASSWORD).status_code == 401
    assert login(admin, OLD_ADMIN_PASSWORD).status_code == 200
    final = admin.get(f"{IMPORTS}/{upload_id}/status").json()["data"]
    assert final["status"] == "done", final["error"]
    assert final["report"]["accounts"]["will_restore"] is True


def test_tampered_accounts_file_is_rejected(admin, backup, tmp_path):
    tampered = tmp_path / "篡改.zip"
    with zipfile.ZipFile(backup) as source, zipfile.ZipFile(tampered, "w") as target:
        for info in source.infolist():
            data = source.read(info)
            if info.filename == ACCOUNTS_MEMBER:
                # 等长改写：只有校验和能发现（成员提权为管理员）
                data = data.replace(b'"role": "member"', b'"role": "admin "')
            target.writestr(info.filename, data)
    upload_id = _upload(admin, tampered.read_bytes())

    response = complete(admin, upload_id)

    assert response.status_code == 400
    assert "校验和不符" in response.json()["error"]
