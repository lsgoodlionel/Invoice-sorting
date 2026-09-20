"""控制面签发：核对授权记录后用私钥签出令牌。

拒绝的原因统一为面向客户的简短文案，不暴露记录是否存在等内部细节。
首次校验成功时把授权绑定到该实例，之后其他实例再来校验一律拒绝。
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.common.errors import AppError
from invoice_sorting.control.models import LICENSE_STATUS_ACTIVE, LicenseRecord
from invoice_sorting.db.models import TZ, now
from invoice_sorting.licensing.constants import (
    MSG_LICENSE_BOUND,
    MSG_LICENSE_EXPIRED,
    MSG_LICENSE_REJECTED,
    MSG_SIGNING_UNAVAILABLE,
)
from invoice_sorting.licensing.keys import load_private_key
from invoice_sorting.licensing.token import LicenseClaims, encode_token

logger = logging.getLogger(__name__)

REJECTED_STATUS = 403
UNAVAILABLE_STATUS = 503


@dataclass(frozen=True)
class IssueRequest:
    """私有化实例提交的校验信息（用量字段仅用于记录与后续运营统计）。"""

    license_key: str
    instance_id: str
    app_version: str = ""
    users: int = 0
    tenants: int = 0


def issue_license_token(db: Session, request: IssueRequest, moment: datetime | None = None) -> str:
    """校验授权记录并签发令牌；调用方负责提交事务。"""
    private_key = load_private_key()
    if private_key is None:
        raise AppError(MSG_SIGNING_UNAVAILABLE, status_code=UNAVAILABLE_STATUS)
    issued_at = moment or now()
    record = _require_record(db, request.license_key, issued_at.date())
    _bind_instance(record, request.instance_id)
    record.issued_at = issued_at
    record.checked_at = issued_at
    claims = LicenseClaims(
        license_key=record.license_key,
        instance_id=request.instance_id,
        valid_until=_end_of_day(record.valid_until),
        max_users=record.max_users,
        features=dict(record.features or {}),
        issued_at=issued_at,
    )
    logger.info("已签发授权令牌：客户=%s 实例=%s", record.customer_name, request.instance_id)
    return encode_token(claims, private_key)


def _require_record(db: Session, license_key: str, today: date) -> LicenseRecord:
    record = db.scalar(select(LicenseRecord).where(LicenseRecord.license_key == license_key))
    if record is None or record.status != LICENSE_STATUS_ACTIVE:
        raise AppError(MSG_LICENSE_REJECTED, status_code=REJECTED_STATUS)
    if record.valid_until is not None and record.valid_until < today:
        raise AppError(MSG_LICENSE_EXPIRED, status_code=REJECTED_STATUS)
    return record


def _bind_instance(record: LicenseRecord, instance_id: str) -> None:
    """首次校验绑定实例；换机需要平台管理员清空 bound_instance_id（批次四）。"""
    if not record.bound_instance_id:
        record.bound_instance_id = instance_id
        return
    if record.bound_instance_id != instance_id:
        raise AppError(MSG_LICENSE_BOUND, status_code=REJECTED_STATUS)


def _end_of_day(value: date | None) -> datetime | None:
    """有效期到当天 23:59:59（Asia/Shanghai）；为空表示永久授权。"""
    if value is None:
        return None
    return datetime.combine(value, time(23, 59, 59), tzinfo=TZ)
