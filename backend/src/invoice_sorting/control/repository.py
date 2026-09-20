"""控制库数据访问：租户、账号与成员的创建与查询（本批只做基础仓储，不含业务流程）。"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.common.errors import AppError, ConflictError
from invoice_sorting.control.models import (
    ROLE_MEMBER,
    TENANT_STATUS_ACTIVE,
    Account,
    Membership,
    Tenant,
)

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")
USERNAME_MAX = 120

MSG_SLUG_INVALID = "账套标识只能使用小写字母、数字与连字符，且不超过 50 个字符"
MSG_SLUG_TAKEN = "账套标识已被占用"
MSG_USERNAME_TAKEN = "用户名已被占用"
MSG_USERNAME_EMPTY = "用户名不能为空"


def normalize_slug(slug: str) -> str:
    return (slug or "").strip().lower()


def normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def is_valid_slug(slug: str) -> bool:
    """slug 只允许小写字母、数字与连字符——顺带挡住路径穿越等构造。"""
    return bool(SLUG_PATTERN.match(normalize_slug(slug)))


def require_slug(slug: str) -> str:
    """校验并返回规范化的 slug；非法时抛出面向用户的错误。"""
    normalized = normalize_slug(slug)
    if not is_valid_slug(normalized):
        raise AppError(MSG_SLUG_INVALID, status_code=400)
    return normalized


def find_tenant(db: Session, slug: str) -> Tenant | None:
    normalized = normalize_slug(slug)
    if not normalized:
        return None
    return db.scalar(select(Tenant).where(Tenant.slug == normalized))


def get_tenant(db: Session, tenant_id: int) -> Tenant | None:
    return db.get(Tenant, tenant_id)


def list_tenants(db: Session, only_active: bool = False) -> list[Tenant]:
    query = select(Tenant).order_by(Tenant.id)
    if only_active:
        query = query.where(Tenant.status == TENANT_STATUS_ACTIVE)
    return list(db.scalars(query))


def create_tenant(db: Session, slug: str, name: str, plan_id: int | None = None) -> Tenant:
    """开通租户；slug 重复时 409。调用方负责提交。"""
    normalized = require_slug(slug)
    if find_tenant(db, normalized) is not None:
        raise ConflictError(MSG_SLUG_TAKEN)
    tenant = Tenant(slug=normalized, name=name or normalized, plan_id=plan_id)
    db.add(tenant)
    db.flush()
    return tenant


def ensure_tenant(db: Session, slug: str, name: str) -> Tenant:
    """幂等：已存在则原样返回（不覆盖名称与状态），否则创建。"""
    found = find_tenant(db, slug)
    return found if found is not None else create_tenant(db, slug, name)


def find_account(db: Session, username: str) -> Account | None:
    normalized = normalize_username(username)
    if not normalized:
        return None
    return db.scalar(select(Account).where(Account.username == normalized))


def get_account(db: Session, account_id: int) -> Account | None:
    return db.get(Account, account_id)


def create_account(
    db: Session,
    username: str,
    display_name: str,
    password_hash: str | None = None,
    is_platform_admin: bool = False,
    account_id: int | None = None,
) -> Account:
    """新建账号；用户名重复时 409。account_id 用于升级迁移时保持业务库中的 id。"""
    normalized = normalize_username(username)
    if not normalized:
        raise AppError(MSG_USERNAME_EMPTY, status_code=400)
    if find_account(db, normalized) is not None:
        raise ConflictError(MSG_USERNAME_TAKEN)
    account = Account(
        id=account_id,
        username=normalized[:USERNAME_MAX],
        display_name=display_name or normalized,
        password_hash=password_hash,
        is_platform_admin=is_platform_admin,
    )
    db.add(account)
    db.flush()
    return account


def find_membership(db: Session, account_id: int, tenant_id: int) -> Membership | None:
    return db.scalar(
        select(Membership).where(
            Membership.account_id == account_id, Membership.tenant_id == tenant_id
        )
    )


def list_memberships(db: Session, account_id: int) -> list[Membership]:
    return list(
        db.scalars(
            select(Membership)
            .where(Membership.account_id == account_id, Membership.is_active.is_(True))
            .order_by(Membership.id)
        )
    )


def ensure_membership(
    db: Session,
    account_id: int,
    tenant_id: int,
    role: str = ROLE_MEMBER,
    is_active: bool = True,
) -> Membership:
    """幂等：已存在则原样返回（不改角色与状态），否则创建。"""
    found = find_membership(db, account_id, tenant_id)
    if found is not None:
        return found
    membership = Membership(
        account_id=account_id, tenant_id=tenant_id, role=role, is_active=is_active
    )
    db.add(membership)
    db.flush()
    return membership
