"""授权记录 API（仅平台管理员）：签发、修改、吊销、解绑实例与删除。

密钥原文只在签发响应里出现一次，列表与详情一律脱敏为前后各 4 位。
"""

from typing import Any

from fastapi import APIRouter

from invoice_sorting.common.errors import ok
from invoice_sorting.control.deps import ControlSessionDep
from invoice_sorting.control.platform_deps import PLATFORM_ADMIN_ONLY
from invoice_sorting.platform_admin.licenses import (
    create_record,
    delete_record,
    list_records,
    require_record,
    unbind_instance,
    update_record,
)
from invoice_sorting.platform_admin.schemas import LicenseCreate, LicenseUpdate
from invoice_sorting.platform_admin.serializers import serialize_license

router = APIRouter(
    prefix="/api/platform/licenses", tags=["平台授权"], dependencies=PLATFORM_ADMIN_ONLY
)


@router.get("")
def read_licenses(control: ControlSessionDep) -> dict[str, Any]:
    return ok([serialize_license(record) for record in list_records(control)])


@router.post("")
def post_license(body: LicenseCreate, control: ControlSessionDep) -> dict[str, Any]:
    """签发一张新授权；请把返回的密钥原文交给客户，之后无法再次查看。"""
    record, key = create_record(control, body)
    return ok(serialize_license(record, key))


@router.patch("/{record_id}")
def patch_license(
    record_id: int, body: LicenseUpdate, control: ControlSessionDep
) -> dict[str, Any]:
    """改客户名、用户数、有效期、备注，或把状态改为 revoked 吊销。"""
    return ok(serialize_license(update_record(control, require_record(control, record_id), body)))


@router.post("/{record_id}/unbind")
def post_unbind(record_id: int, control: ControlSessionDep) -> dict[str, Any]:
    """解绑已绑定的实例，供客户换机后重新校验。"""
    return ok(serialize_license(unbind_instance(control, require_record(control, record_id))))


@router.delete("/{record_id}")
def remove_license(record_id: int, control: ControlSessionDep) -> dict[str, Any]:
    delete_record(control, require_record(control, record_id))
    return ok(None)
