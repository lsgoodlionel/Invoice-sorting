"""接口形状（docs/api-contract.md「注册申请与推荐」一节）。

申请详情与推荐记录只给平台管理员；推荐人自己只能看到脱敏邮箱与状态，看不到需求等资料。
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.attachments.serializers import iso_datetime
from invoice_sorting.control.models import Account, Tenant
from invoice_sorting.control.signup_models import (
    ReferralCode,
    SignupApplication,
    SignupSettings,
)
from invoice_sorting.signup.codes import application_number, mask_email
from invoice_sorting.signup.review import Delivery


@dataclass(frozen=True)
class Lookup:
    """一批申请关联到的账号、账套与推荐资格，批量查询一次，避免 N+1。"""

    accounts: dict[int, Account]
    tenants: dict[int, Tenant]
    disabled_referrers: frozenset[int] = frozenset()


def build_lookup(control: Session, applications: list[SignupApplication]) -> Lookup:
    account_ids = {
        value
        for item in applications
        for value in (
            item.referrer_account_id,
            item.reviewer_account_id,
            item.registered_account_id,
        )
        if value is not None
    }
    tenant_ids = {item.registered_tenant_id for item in applications if item.registered_tenant_id}
    accounts = _by_id(control, Account, account_ids)
    tenants = _by_id(control, Tenant, tenant_ids)
    disabled = control.scalars(
        select(ReferralCode.account_id).where(
            ReferralCode.account_id.in_(account_ids), ReferralCode.is_disabled.is_(True)
        )
    )
    return Lookup(accounts=accounts, tenants=tenants, disabled_referrers=frozenset(disabled))


def _by_id(control: Session, model: Any, ids: set[int]) -> dict[int, Any]:
    if not ids:
        return {}
    return {row.id: row for row in control.scalars(select(model).where(model.id.in_(ids)))}


def account_ref(account: Account | None) -> dict[str, Any] | None:
    if account is None:
        return None
    return {
        "account_id": account.id,
        "username": account.username,
        "display_name": account.display_name,
    }


def tenant_ref(tenant: Tenant | None) -> dict[str, Any] | None:
    return {"slug": tenant.slug, "name": tenant.name} if tenant is not None else None


def _approved(item: SignupApplication) -> dict[str, Any] | None:
    if not item.approved_slug:
        return None
    return {
        "slug": item.approved_slug,
        "name": item.approved_name,
        "plan_code": item.approved_plan_code or None,
        "expires_on": item.approved_expires_on.isoformat() if item.approved_expires_on else None,
    }


def serialize_application(item: SignupApplication, lookup: Lookup) -> dict[str, Any]:
    referrer = lookup.accounts.get(item.referrer_account_id or 0)
    return {
        "id": item.id,
        "number": application_number(item.id),
        "name": item.name,
        "email": item.email,
        "identity": item.identity,
        "needs": item.needs,
        "ledger_name": item.ledger_name,
        "status": item.status,
        "referrer": account_ref(referrer),
        "is_auto_approved": item.is_auto_approved,
        "reviewer": account_ref(lookup.accounts.get(item.reviewer_account_id or 0)),
        "reviewed_at": iso_datetime(item.reviewed_at),
        "reject_reason": item.reject_reason,
        "approved": _approved(item),
        "code_expires_at": iso_datetime(item.code_expires_at),
        "mail_status": item.mail_status,
        "mail_error": item.mail_error,
        "mail_sent_at": iso_datetime(item.mail_sent_at),
        "tenant": tenant_ref(lookup.tenants.get(item.registered_tenant_id or 0)),
        "registered_at": iso_datetime(item.registered_at),
        "is_purged": item.is_purged,
        "created_at": iso_datetime(item.created_at),
    }


def serialize_delivery(delivery: Delivery) -> dict[str, Any]:
    """link 与 text 只在没发出去（未配置 SMTP 或发送失败）时给出，供管理员转告。"""
    return {
        "mail_status": delivery.status,
        "mail_error": delivery.error,
        "link": delivery.link or None,
        "text": delivery.text or None,
    }


def serialize_settings(row: SignupSettings, is_mail_configured: bool) -> dict[str, Any]:
    return {
        "require_approval": row.require_approval,
        "monthly_referral_quota": row.monthly_referral_quota,
        "code_valid_days": row.code_valid_days,
        "is_mail_configured": is_mail_configured,
        "updated_at": iso_datetime(row.updated_at),
    }


def serialize_my_referral(item: SignupApplication) -> dict[str, Any]:
    """推荐人视角：只有脱敏邮箱、状态与时间。"""
    return {
        "id": item.id,
        "email_masked": mask_email(item.email) if item.email else "",
        "status": item.status,
        "created_at": iso_datetime(item.created_at),
        "registered_at": iso_datetime(item.registered_at),
    }


def serialize_referral_record(item: SignupApplication, lookup: Lookup) -> dict[str, Any]:
    """平台视角的推荐记录（实名）：推荐人、被推荐人邮箱、账套、时间与结果。"""
    referrer_id = item.referrer_account_id or 0
    return {
        "application_id": item.id,
        "number": application_number(item.id),
        "referrer": account_ref(lookup.accounts.get(referrer_id)),
        "is_referrer_disabled": referrer_id in lookup.disabled_referrers,
        "referee_email": item.email,
        "tenant": tenant_ref(lookup.tenants.get(item.registered_tenant_id or 0)),
        "status": item.status,
        "is_auto_approved": item.is_auto_approved,
        "created_at": iso_datetime(item.created_at),
        "registered_at": iso_datetime(item.registered_at),
    }
