"""租户成员查询：某租户内的账号与角色。

跨租户越权是本模块的首要风险，因此所有查询都必须带 tenant_id，
不提供“按账号 id 直接取账号”的租户无关入口给业务路由使用。
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.control.models import ROLE_ADMIN, Account, Membership

BUILTIN_ADMIN_USERNAME = "admin"


@dataclass(frozen=True)
class Member:
    """账号在某租户内的完整身份；is_active 同时受账号与成员关系约束。"""

    account: Account
    membership: Membership

    @property
    def id(self) -> int:
        return self.account.id

    @property
    def role(self) -> str:
        return self.membership.role

    @property
    def is_active(self) -> bool:
        return bool(self.account.is_active and self.membership.is_active)


def find_member(control: Session, account_id: int, tenant_id: int) -> Member | None:
    """账号在该租户内的身份；没有成员关系时返回 None（据此拒绝越权访问）。"""
    row = control.execute(
        select(Account, Membership)
        .join(Membership, Membership.account_id == Account.id)
        .where(Membership.account_id == account_id, Membership.tenant_id == tenant_id)
    ).first()
    return Member(account=row[0], membership=row[1]) if row is not None else None


def active_member(control: Session, account_id: int, tenant_id: int) -> Member | None:
    """仅返回可用的成员（账号启用且成员关系启用）。"""
    member = find_member(control, account_id, tenant_id)
    return member if member is not None and member.is_active else None


def list_members(control: Session, tenant_id: int) -> list[Member]:
    rows = control.execute(
        select(Account, Membership)
        .join(Membership, Membership.account_id == Account.id)
        .where(Membership.tenant_id == tenant_id)
        .order_by(Membership.id)
    ).all()
    return [Member(account=row[0], membership=row[1]) for row in rows]


def count_ready_admins(control: Session, tenant_id: int, exclude_id: int | None = None) -> int:
    """该租户内启用中且已设置密码的管理员数量（可排除某人，用于预判修改后的状态）。"""
    members = list_members(control, tenant_id)
    return sum(
        1
        for member in members
        if member.role == ROLE_ADMIN
        and member.is_active
        and member.account.password_hash is not None
        and member.id != exclude_id
    )


def builtin_admin(control: Session, tenant_id: int) -> Member | None:
    """该租户内的内置管理员 admin（单租户部署一定有；SaaS 租户通常没有）。"""
    members = list_members(control, tenant_id)
    return next((m for m in members if m.account.username == BUILTIN_ADMIN_USERNAME), None)


def has_password_set(control: Session, tenant_id: int) -> bool:
    """是否已完成“设置初始密码”。

    沿用单租户语义：看内置管理员 admin 是否已有密码。SaaS 租户由平台开通成员、
    没有内置 admin，一律视为已完成，前端直接显示登录表单。
    """
    admin = builtin_admin(control, tenant_id)
    return admin is None or admin.account.password_hash is not None
