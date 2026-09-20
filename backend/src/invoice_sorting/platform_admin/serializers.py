"""平台后台的接口形状（docs/api-contract.md「平台运营后台」一节）。

授权密钥只在**签发的那一次**返回原文，之后一律脱敏为前后各 4 位，
且任何日志都不写入密钥本身。
"""

from typing import Any

from invoice_sorting.attachments.serializers import iso_datetime
from invoice_sorting.control.models import Invite, LicenseRecord, Plan, Tenant, UsageSnapshot

MASK = "****"
KEEP_CHARS = 4
MASK_MIN_LENGTH = KEEP_CHARS * 2


def mask_license_key(key: str) -> str:
    """只显示前后各 4 位；过短的密钥整体隐藏。"""
    text = key or ""
    if len(text) <= MASK_MIN_LENGTH:
        return MASK
    return f"{text[:KEEP_CHARS]}{MASK}{text[-KEEP_CHARS:]}"


def serialize_plan(plan: Plan) -> dict[str, Any]:
    return {
        "id": plan.id,
        "code": plan.code,
        "name": plan.name,
        "max_users": plan.max_users,
        "max_storage_mb": plan.max_storage_mb,
        "max_expenses_per_month": plan.max_expenses_per_month,
        "features": dict(plan.features or {}),
        "created_at": iso_datetime(plan.created_at),
    }


def plan_brief(plan: Plan | None) -> dict[str, Any] | None:
    return {"code": plan.code, "name": plan.name} if plan is not None else None


def serialize_usage(usage: UsageSnapshot | None) -> dict[str, Any] | None:
    if usage is None:
        return None
    return {
        "day": usage.day.isoformat(),
        "users": usage.users,
        "storage_bytes": usage.storage_bytes,
        "expenses_created": usage.expenses_created,
    }


def serialize_tenant(
    tenant: Tenant,
    plan: Plan | None = None,
    member_count: int = 0,
    usage: UsageSnapshot | None = None,
) -> dict[str, Any]:
    return {
        "slug": tenant.slug,
        "name": tenant.name,
        "status": tenant.status,
        "plan": plan_brief(plan),
        "expires_on": tenant.expires_on.isoformat() if tenant.expires_on else None,
        "member_count": member_count,
        "usage": serialize_usage(usage),
        "created_at": iso_datetime(tenant.created_at),
    }


def serialize_invite(invite: Invite) -> dict[str, Any]:
    return {
        "id": invite.id,
        "code": invite.code,
        "role": invite.role,
        "expires_on": invite.expires_on.isoformat() if invite.expires_on else None,
        "is_used": invite.used_by is not None,
        "created_at": iso_datetime(invite.created_at),
    }


def serialize_license(record: LicenseRecord, key: str | None = None) -> dict[str, Any]:
    """key 只在签发时传入（原文只出现这一次），其余场景一律脱敏。"""
    return {
        "id": record.id,
        "license_key": key if key is not None else mask_license_key(record.license_key),
        "is_key_visible": key is not None,
        "customer_name": record.customer_name,
        "max_users": record.max_users,
        "valid_until": record.valid_until.isoformat() if record.valid_until else None,
        "status": record.status,
        "bound_instance_id": record.bound_instance_id,
        "note": record.note,
        "issued_at": iso_datetime(record.issued_at),
        "checked_at": iso_datetime(record.checked_at),
        "created_at": iso_datetime(record.created_at),
    }
