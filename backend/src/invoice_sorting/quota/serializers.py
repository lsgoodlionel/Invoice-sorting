"""额度接口的数据形状（GET /api/quota 的 data）。"""

from dataclasses import asdict
from datetime import date
from typing import Any

from invoice_sorting.attachments.serializers import iso_datetime
from invoice_sorting.quota.plans import PlanLimits
from invoice_sorting.quota.state import QuotaReport
from invoice_sorting.quota.usage import QuotaUsage


def serialize_plan(plan: PlanLimits) -> dict[str, Any]:
    return {
        "code": plan.code,
        "name": plan.name,
        "max_users": plan.max_users,
        "max_storage_mb": plan.max_storage_mb,
        "max_expenses_per_month": plan.max_expenses_per_month,
        "features": dict(plan.features),
    }


def serialize_usage(usage: QuotaUsage) -> dict[str, Any]:
    return {
        "users": usage.users,
        "storage_bytes": usage.storage_bytes,
        "storage_mb": usage.storage_mb,
        "expenses_this_month": usage.expenses_this_month,
        "measured_at": iso_datetime(usage.storage_measured_at),
        "is_stale": usage.storage_is_stale,
    }


def _days_until(expires_on: date | None, today: date) -> int | None:
    return None if expires_on is None else (expires_on - today).days


def serialize_report(report: QuotaReport, today: date) -> dict[str, Any]:
    """单账套部署下 enforced 为 false，plan/limits/usage 一律为空，界面不显示任何上限。"""
    return {
        "enforced": report.is_enforced,
        "plan": serialize_plan(report.plan) if report.plan else None,
        "usage": serialize_usage(report.usage) if report.usage else None,
        "limits": [asdict(line) for line in report.lines],
        "is_readonly": report.is_readonly,
        "readonly_reason": report.notice.reason,
        "readonly_message": report.notice.message,
        "status": report.status,
        "expires_on": report.expires_on.isoformat() if report.expires_on else None,
        "expires_in_days": _days_until(report.expires_on, today),
    }
