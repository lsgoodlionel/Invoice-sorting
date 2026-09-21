"""网页导入测试辅助：造一个真实的搬迁包、按分片上传、改会话时间模拟过期。

测试数据全部虚构；包里额外放一个随机内容的大文件，保证能切成两片以上。
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from invoice_sorting.migration.export import export_tenant
from invoice_sorting.migration.upload_store import SESSION_FILENAME, STAGING_DIRNAME
from tests.migration_helpers import seed_tenant_data

IMPORTS = "/api/backup/imports"
PART = 64 * 1024  # 最小分片，测试用小片保证两片以上
FILLER_NAME = "虚构大附件.bin"
FILLER_BYTES = 100 * 1024


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_package(app: Any, session, settings, tmp_path: Path, slug: str = "default") -> bytes:
    """在账套里写入虚构数据与一个不可压缩的大文件，导出成搬迁包字节。"""
    seed_tenant_data(session, settings, tmp_path / "来源")
    filler = settings.library_dir / FILLER_NAME
    filler.parent.mkdir(parents=True, exist_ok=True)
    filler.write_bytes(os.urandom(FILLER_BYTES))
    out = tmp_path / "搬迁包.zip"
    export_tenant(app.state.tenants.get(slug), out, tenant_name="虚构来源账套")
    return out.read_bytes()


def create_body(data: bytes, part_size: int = PART, **overrides: Any) -> dict[str, Any]:
    body = {
        "filename": "账本.zip",
        "size": len(data),
        "part_size": part_size,
        "sha256": digest(data),
    }
    return {**body, **overrides}


def create_upload(client, data: bytes, base: str = IMPORTS, headers=None, **overrides) -> dict:
    response = client.post(base, json=create_body(data, **overrides), headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def split(data: bytes, part_size: int = PART) -> list[bytes]:
    return [data[start : start + part_size] for start in range(0, len(data), part_size)] or [b""]


def put_part(client, upload_id: str, index: int, chunk: bytes, base: str = IMPORTS, headers=None):
    return client.put(
        f"{base}/{upload_id}/parts/{index}",
        content=chunk,
        headers={"Content-Type": "application/octet-stream", **(headers or {})},
    )


def upload_all(client, upload_id: str, data: bytes, base: str = IMPORTS, headers=None) -> None:
    for index, chunk in enumerate(split(data)):
        response = put_part(client, upload_id, index, chunk, base=base, headers=headers)
        assert response.status_code == 200, response.text


def complete(client, upload_id: str, base: str = IMPORTS, headers=None, **body):
    return client.post(f"{base}/{upload_id}/complete", json=body or None, headers=headers)


def uploaded(client, data: bytes, base: str = IMPORTS, headers=None) -> str:
    """登记 + 全部上传 + 完成合并，返回 upload_id。"""
    upload_id = create_upload(client, data, base=base, headers=headers)["upload_id"]
    upload_all(client, upload_id, data, base=base, headers=headers)
    response = complete(client, upload_id, base=base, headers=headers)
    assert response.status_code == 200, response.text
    return upload_id


def session_dir(settings, upload_id: str, slug: str = "default") -> Path:
    return settings.for_tenant(slug).data_dir / STAGING_DIRNAME / upload_id


def age_session(settings, upload_id: str, hours: int, slug: str = "default") -> None:
    """把会话创建时间往前拨，模拟长时间未完成的上传。"""
    from datetime import timedelta

    from invoice_sorting.db.models import now

    path = session_dir(settings, upload_id, slug) / SESSION_FILENAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["created_at"] = (now() - timedelta(hours=hours)).isoformat()
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
