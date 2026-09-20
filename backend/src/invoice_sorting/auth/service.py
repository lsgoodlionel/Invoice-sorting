"""认证业务（控制库）：admin 初始密码、用户名密码登录、修改本人密码、命令行重置。

登录统一在控制面账号上完成，会话记录当前所选租户；业务库 `app_user` 只是镜像。
拿不到租户上下文时一律失败，不会退回任何默认库。
"""

import threading
from dataclasses import dataclass
from functools import cache

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from invoice_sorting.auth.context import AuthUser
from invoice_sorting.auth.passwords import hash_password, verify_password
from invoice_sorting.auth.sessions import (
    MSG_NOT_A_MEMBER,
    create_session,
    delete_account_sessions,
    member_user,
    purge_expired,
)
from invoice_sorting.common.errors import AppError, ConflictError, NotFoundError
from invoice_sorting.control.members import (
    Member,
    active_member,
    builtin_admin,
    find_member,
    has_password_set,
)
from invoice_sorting.control.models import TENANT_STATUS_ACTIVE, Account, Membership, Tenant
from invoice_sorting.control.repository import find_account, get_tenant
from invoice_sorting.db.models import now

MSG_NEED_SETUP = "请先设置初始密码"
MSG_LOGIN_REQUIRED = "请先登录"
MSG_ALREADY_SET = "已设置过初始密码，请直接登录"
MSG_WRONG_CREDENTIALS = "用户名或密码错误"
MSG_WRONG_CURRENT = "当前密码错误"
MSG_NO_TENANT = "当前账号尚未加入任何账套，请联系管理员开通"

# 同进程内串行化初始密码设置；条件 UPDATE（仅当密码为空）兜底跨进程并发
_setup_lock = threading.Lock()


@dataclass(frozen=True)
class Grant:
    """登录成功：明文会话令牌、租户内身份快照与所选租户。"""

    token: str
    user: AuthUser
    member: Member
    tenant: Tenant


@cache
def _dummy_hash() -> str:
    """用户不存在或未设置密码时也做一次同等代价的哈希校验，避免计时差异泄露用户名。"""
    return hash_password("invoice-sorting-dummy-password")


def is_password_set(control: Session, tenant_id: int) -> bool:
    return has_password_set(control, tenant_id)


def start_session(control: Session, member: Member, tenant: Tenant, user_agent: str) -> Grant:
    """写入登录时间、清理过期会话并签发新会话。"""
    member.account.last_login_at = now()
    purge_expired(control)
    token = create_session(control, member.id, tenant.id, user_agent)
    return Grant(token=token, user=member_user(member), member=member, tenant=tenant)


def setup_initial_password(
    control: Session, tenant: Tenant, password: str, user_agent: str
) -> Grant:
    """为本账套的内置管理员 admin 设置初始密码并登录。已设置过时 409。"""
    encoded = hash_password(password)  # 慢哈希放在锁外
    with _setup_lock:
        admin = builtin_admin(control, tenant.id)
        if admin is None:
            control.rollback()
            raise ConflictError(MSG_ALREADY_SET)
        statement = (
            update(Account)
            .where(Account.id == admin.id, Account.password_hash.is_(None))
            .values(password_hash=encoded)
            .execution_options(synchronize_session=False)
        )
        if control.execute(statement).rowcount != 1:
            control.rollback()
            raise ConflictError(MSG_ALREADY_SET)
        control.refresh(admin.account)
        grant = start_session(control, admin, tenant, user_agent)
        control.commit()
    return grant


def _require_setup(control: Session, tenant: Tenant | None) -> None:
    if tenant is not None and not is_password_set(control, tenant.id):
        raise ConflictError(MSG_NEED_SETUP)


def authenticate(control: Session, username: str, password: str) -> Account | None:
    """用户名不存在、未设置密码、密码错误或账号停用均返回 None（统一对外错误）。"""
    account = find_account(control, username)
    encoded = account.password_hash if account is not None else None
    is_match = verify_password(password, encoded or _dummy_hash())
    if account is None or encoded is None or not is_match or not account.is_active:
        return None
    return account


def _is_usable(tenant: Tenant | None) -> bool:
    # 租户状态与额度的完整校验在批次三；这里只挡住已停用/关闭的账套
    return tenant is not None and tenant.status == TENANT_STATUS_ACTIVE


def memberships_of(control: Session, account_id: int, only_active: bool = False):
    query = select(Membership).where(Membership.account_id == account_id)
    if only_active:
        query = query.where(Membership.is_active.is_(True))
    return list(control.scalars(query.order_by(Membership.id)))


def account_tenants(control: Session, account_id: int) -> list[Tenant]:
    """账号可进入的账套：成员关系启用且账套可用，按加入顺序排列。"""
    rows = memberships_of(control, account_id, only_active=True)
    tenants = [get_tenant(control, row.tenant_id) for row in rows]
    return [tenant for tenant in tenants if _is_usable(tenant)]


def resolve_login_tenant(
    control: Session, account: Account, tenant: Tenant | None
) -> Member | None:
    """定位登录后要进入的账套。

    完全不是该账套成员 → 403 并给出明确文案（例如走错了子域名）；
    成员关系存在但已被停用 → 返回 None，沿用“用户名或密码错误”的统一口径，不泄露账号状态。
    """
    if tenant is not None:
        member = find_member(control, account.id, tenant.id)
        if member is None:
            raise AppError(MSG_NOT_A_MEMBER, status_code=403)
        return member if member.is_active and _is_usable(tenant) else None
    if not memberships_of(control, account.id):
        raise AppError(MSG_NO_TENANT, status_code=403)
    available = account_tenants(control, account.id)
    return active_member(control, account.id, available[0].id) if available else None


def login_with_password(
    control: Session, tenant: Tenant | None, username: str, password: str, user_agent: str
) -> Grant | None:
    """凭据正确返回会话；错误返回 None（由调用方计入失败次数）。admin 未设置密码时 409。"""
    _require_setup(control, tenant)
    account = authenticate(control, username, password)
    if account is None:
        return None
    member = resolve_login_tenant(control, account, tenant)
    if member is None:
        return None
    target = tenant if tenant is not None else get_tenant(control, member.membership.tenant_id)
    return start_session(control, member, target, user_agent)


def change_password(
    control: Session, account_id: int, current: str, new: str, keep_token: str | None
) -> None:
    """修改本人密码；本人其他会话失效，当前会话保留。"""
    account = control.get(Account, account_id)
    if account is None:
        raise NotFoundError("用户")
    if not verify_password(current, account.password_hash):
        raise AppError(MSG_WRONG_CURRENT, status_code=400)
    account.password_hash = hash_password(new)
    delete_account_sessions(control, account.id, keep_token)
    control.flush()


def reset_credentials(control: Session, username: str) -> bool:
    """清除指定账号的密码与全部会话；账号不存在返回 False（命令行用）。"""
    account = find_account(control, username)
    if account is None:
        return False
    account.password_hash = None
    delete_account_sessions(control, account.id)
    control.flush()
    return True
