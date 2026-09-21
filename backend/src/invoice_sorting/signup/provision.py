"""批准时确定“将来开通什么样的账套”：标识、名称、套餐与到期日。

真正的开通发生在申请人凭注册码完成注册时，复用 platform_admin.tenants.open_tenant，
这里只负责挑一个可用的标识并做占用检查（已开通的账套 + 其他已批准未注册的申请）。
"""

import re
import secrets
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.common.errors import AppError, ConflictError
from invoice_sorting.control.repository import MSG_SLUG_TAKEN, find_tenant, require_slug
from invoice_sorting.control.signup_models import APPLICATION_APPROVED, SignupApplication
from invoice_sorting.platform_admin.plans import find_plan, require_plan_by_code
from invoice_sorting.quota.plans import FREE_PLAN
from invoice_sorting.signup.constants import LEDGER_NAME_MAX, MSG_SLUG_RESERVED

SLUG_BASE_MAX = 20
SLUG_SUFFIX_BYTES = 3
SLUG_FALLBACK_BASE = "ledger"
MAX_SLUG_ATTEMPTS = 8
MSG_SLUG_EXHAUSTED = "暂时无法生成可用的账套标识，请稍后再试"


@dataclass(frozen=True)
class TenantOptions:
    """批准时平台管理员可改的开通参数；None 表示用默认值。"""

    slug: str | None = None
    name: str | None = None
    plan_code: str | None = None
    expires_on: date | None = None


@dataclass(frozen=True)
class TenantPlan:
    slug: str
    name: str
    plan_code: str
    expires_on: date | None


def is_slug_reserved(control: Session, slug: str, exclude_id: int | None = None) -> bool:
    query = select(SignupApplication.id).where(
        SignupApplication.status == APPLICATION_APPROVED,
        SignupApplication.approved_slug == slug,
    )
    if exclude_id is not None:
        query = query.where(SignupApplication.id != exclude_id)
    return control.scalar(query.limit(1)) is not None


def is_slug_free(control: Session, slug: str, exclude_id: int | None = None) -> bool:
    return find_tenant(control, slug) is None and not is_slug_reserved(control, slug, exclude_id)


def _slug_base(email: str) -> str:
    local = (email or "").partition("@")[0].lower()
    base = re.sub(r"[^a-z0-9]+", "-", local).strip("-")[:SLUG_BASE_MAX].strip("-")
    return base or SLUG_FALLBACK_BASE


def auto_slug(control: Session, email: str, exclude_id: int | None = None) -> str:
    """邮箱前缀 + 随机后缀，例如 zhang-3fa9c1；避开已开通与已预留的标识。"""
    base = _slug_base(email)
    for _ in range(MAX_SLUG_ATTEMPTS):
        candidate = f"{base}-{secrets.token_hex(SLUG_SUFFIX_BYTES)}"
        if is_slug_free(control, candidate, exclude_id):
            return candidate
    raise AppError(MSG_SLUG_EXHAUSTED, status_code=503)


def default_ledger_name(application: SignupApplication) -> str:
    fallback = f"{application.name}的账本" if application.name else "我的账本"
    return (application.ledger_name or fallback)[:LEDGER_NAME_MAX]


def _checked_slug(control: Session, slug: str, exclude_id: int) -> str:
    normalized = require_slug(slug)
    if find_tenant(control, normalized) is not None:
        raise ConflictError(MSG_SLUG_TAKEN)
    if is_slug_reserved(control, normalized, exclude_id):
        raise ConflictError(MSG_SLUG_RESERVED)
    return normalized


def _plan_code(control: Session, requested: str | None) -> str:
    """指定了套餐就必须存在（否则 404）；没指定用默认免费套餐（库里没有时留空，按免费计算）。"""
    if requested:
        return require_plan_by_code(control, requested).code
    return FREE_PLAN.code if find_plan(control, FREE_PLAN.code) is not None else ""


def plan_tenant(
    control: Session, application: SignupApplication, options: TenantOptions
) -> TenantPlan:
    slug = (
        _checked_slug(control, options.slug, application.id)
        if options.slug
        else auto_slug(control, application.email, application.id)
    )
    return TenantPlan(
        slug=slug,
        name=(options.name or default_ledger_name(application))[:LEDGER_NAME_MAX],
        plan_code=_plan_code(control, options.plan_code),
        expires_on=options.expires_on,
    )


def apply_plan(application: SignupApplication, plan: TenantPlan) -> None:
    application.approved_slug = plan.slug
    application.approved_name = plan.name
    application.approved_plan_code = plan.plan_code
    application.approved_expires_on = plan.expires_on
