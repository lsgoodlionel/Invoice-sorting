"""私有化授权记录：签发、修改、吊销、解绑实例与删除。

密钥用 `secrets` 生成，只在签发的那一次返回原文；记录与日志都不输出密钥本身。
"""

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.common.errors import NotFoundError
from invoice_sorting.control.models import LICENSE_STATUS_ACTIVE, LicenseRecord
from invoice_sorting.platform_admin.schemas import LicenseCreate, LicenseUpdate

WHAT_LICENSE = "授权记录"
KEY_BYTES = 24
GROUP_SIZE = 8


def generate_license_key() -> str:
    """分组显示便于客户抄写；字符集来自 token_urlsafe，熵 ≥192 位。"""
    raw = secrets.token_urlsafe(KEY_BYTES).replace("-", "").replace("_", "")
    return "-".join(raw[i : i + GROUP_SIZE] for i in range(0, len(raw), GROUP_SIZE))


def list_records(control: Session) -> list[LicenseRecord]:
    return list(control.scalars(select(LicenseRecord).order_by(LicenseRecord.id.desc())))


def require_record(control: Session, record_id: int) -> LicenseRecord:
    record = control.get(LicenseRecord, record_id)
    if record is None:
        raise NotFoundError(WHAT_LICENSE)
    return record


def create_record(control: Session, body: LicenseCreate) -> tuple[LicenseRecord, str]:
    """返回记录与密钥原文（只有这一次能拿到原文）。"""
    key = generate_license_key()
    record = LicenseRecord(
        license_key=key,
        customer_name=body.customer_name,
        max_users=body.max_users,
        valid_until=body.valid_until,
        status=LICENSE_STATUS_ACTIVE,
        features=dict(body.features),
        note=body.note,
    )
    control.add(record)
    control.flush()
    return record, key


def update_record(control: Session, record: LicenseRecord, body: LicenseUpdate) -> LicenseRecord:
    changed = body.model_fields_set
    if "customer_name" in changed and body.customer_name:
        record.customer_name = body.customer_name
    if "max_users" in changed and body.max_users is not None:
        record.max_users = body.max_users
    if "valid_until" in changed:
        record.valid_until = body.valid_until
    if "status" in changed and body.status is not None:
        record.status = str(body.status)
    if "note" in changed and body.note is not None:
        record.note = body.note
    control.flush()
    return record


def unbind_instance(control: Session, record: LicenseRecord) -> LicenseRecord:
    """解绑实例：客户换机后下次校验会重新绑定新的 instance_id。"""
    record.bound_instance_id = ""
    control.flush()
    return record


def delete_record(control: Session, record: LicenseRecord) -> None:
    control.delete(record)
    control.flush()
