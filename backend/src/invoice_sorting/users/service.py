"""账套内成员管理：创建、修改（姓名/角色/启用）、管理员重置密码、删除。

全部在控制库上操作，且**只针对当前账套**——管理员管不到别的账套的成员
（平台级管理留给批次四）。约束：不能停用自己或把自己改为普通用户；
每个账套至少保留一名启用中且已设置密码的管理员；停用或重置密码后该账号全部会话失效。
删除复用 users/deletion.py（与账号恢复同一套删除语义），删除后仍须留有可用管理员
（口径与账号恢复一致：启用中且有密码，或尚未设密码的内置 admin）。
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from invoice_sorting.auth.context import AuthUser
from invoice_sorting.auth.passwords import hash_password
from invoice_sorting.auth.sessions import delete_account_sessions
from invoice_sorting.common.errors import AppError, ConflictError, NotFoundError
from invoice_sorting.control.members import Member, count_ready_admins, find_member
from invoice_sorting.control.models import ROLE_ADMIN, Membership
from invoice_sorting.control.repository import create_account, find_account
from invoice_sorting.migration.accounts_plan import has_usable_admin
from invoice_sorting.users.deletion import DeletedAccount, delete_account
from invoice_sorting.users.repository import UserRole
from invoice_sorting.users.schemas import UserCreate, UserUpdate

MSG_USERNAME_TAKEN = "用户名已存在"
MSG_CANNOT_DEACTIVATE_SELF = "不能停用自己"
MSG_CANNOT_DEMOTE_SELF = "不能把自己改为普通用户"
MSG_LAST_ADMIN = "系统必须至少保留一名启用中且已设置密码的管理员"
MSG_LAST_ADMIN_DELETE = "不能删除账套里最后一名可用的管理员"


def get_member_or_404(control: Session, tenant_id: int, account_id: int) -> Member:
    """只在当前账套内查找；别的账套的账号一律按“不存在”处理。"""
    member = find_member(control, account_id, tenant_id)
    if member is None:
        raise NotFoundError("用户")
    return member


def create_member(control: Session, tenant_id: int, body: UserCreate) -> Member:
    if find_account(control, body.username) is not None:
        raise ConflictError(MSG_USERNAME_TAKEN)
    try:
        account = create_account(
            control,
            body.username,
            body.display_name or body.username,
            password_hash=hash_password(body.password),
        )
        membership = Membership(
            account_id=account.id, tenant_id=tenant_id, role=str(body.role), is_active=True
        )
        control.add(membership)
        control.flush()
    except (ConflictError, IntegrityError) as exc:  # 并发创建同名账号
        control.rollback()
        raise ConflictError(MSG_USERNAME_TAKEN) from exc
    return Member(account=account, membership=membership)


def _check_self_change(actor: AuthUser | None, member: Member, body: UserUpdate) -> None:
    if actor is None or actor.id != member.id:
        return
    if body.is_active is False:
        raise AppError(MSG_CANNOT_DEACTIVATE_SELF)
    if body.role == UserRole.MEMBER:
        raise AppError(MSG_CANNOT_DEMOTE_SELF)


def _is_ready_admin(role: str, is_active: bool, member: Member) -> bool:
    return role == ROLE_ADMIN and is_active and member.account.password_hash is not None


def _check_admin_remains(control: Session, member: Member, body: UserUpdate) -> None:
    """仅当本次修改让该成员失去“启用中且有密码的管理员”资格时，检查本账套是否还有其他人。"""
    role = str(body.role) if body.role is not None else member.role
    is_active = body.is_active if body.is_active is not None else member.is_active
    if not _is_ready_admin(member.role, member.is_active, member):
        return
    if _is_ready_admin(role, is_active, member):
        return
    if count_ready_admins(control, member.membership.tenant_id, exclude_id=member.id) == 0:
        raise AppError(MSG_LAST_ADMIN)


def update_member(
    control: Session, actor: AuthUser | None, member: Member, body: UserUpdate
) -> Member:
    _check_self_change(actor, member, body)
    _check_admin_remains(control, member, body)
    was_active = member.is_active
    if body.display_name is not None:
        member.account.display_name = body.display_name
    if body.role is not None:
        member.membership.role = str(body.role)
    if body.is_active is not None:
        member.membership.is_active = body.is_active
    if was_active and not member.is_active:
        delete_account_sessions(control, member.id)
    control.flush()
    return member


def reset_member_password(control: Session, member: Member, password: str) -> None:
    member.account.password_hash = hash_password(password)
    delete_account_sessions(control, member.id)
    control.flush()


def delete_member(
    control: Session,
    business: Session | None,
    account_id: int,
    *,
    actor_id: int | None,
    tenant_id: int,
) -> DeletedAccount:
    """删除本账套的成员：只属于本账套时删除账号，还属于别的账套时只移出本账套。

    不能删自己（400）、不在本账套（404）；删完若本账套已没有可用管理员则 409，
    此时两个库都只 flush 过，由调用方回滚。
    """
    get_member_or_404(control, tenant_id, account_id)
    deleted = delete_account(control, business, account_id, actor_id=actor_id, tenant_id=tenant_id)
    if not has_usable_admin(control, tenant_id):
        raise ConflictError(MSG_LAST_ADMIN_DELETE)
    return deleted
