"""多账套部署的首次启动：在网页上创建**首个平台管理员**。

安装命令里不带任何账号信息，第一次打开网页时由使用者设置用户名与密码——与单账套部署
「首次打开网页为 admin 设置初始密码」是同一个入口（POST /api/auth/setup），只是多账套下
创建的是平台管理员，并顺带开通「平台运营」账套。

安全前提（只有空库才允许）：
- 控制库里**一个账号都没有**、且还没有平台运营账套时才放行；
- 一旦有任意账号，接口必须 409，避免任何人事后抢注；
- 同进程内用锁串行化，跨进程由用户名与账套 slug 的唯一约束兜底。
命令行 `grant-platform-admin` 继续可用（忘记密码或批量运维时）。
"""

import threading

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from invoice_sorting.auth.passwords import hash_password
from invoice_sorting.auth.service import Grant, start_session
from invoice_sorting.common.errors import ConflictError
from invoice_sorting.control.members import Member
from invoice_sorting.control.models import ROLE_ADMIN, Account
from invoice_sorting.control.repository import (
    create_account,
    create_tenant,
    ensure_membership,
    find_tenant,
)

PLATFORM_TENANT_SLUG = "platform"
PLATFORM_TENANT_NAME = "平台运营"
MSG_PLATFORM_READY = "已创建过平台管理员，请直接登录"

# 同进程内串行化首次创建；唯一约束（account.username / tenant.slug）兜底跨进程并发
_bootstrap_lock = threading.Lock()


def has_any_account(control: Session) -> bool:
    return bool(control.scalar(select(func.count(Account.id))))


def is_platform_ready(control: Session) -> bool:
    """控制库是否已经初始化过（有账号，或已开通平台运营账套）。"""
    return has_any_account(control) or find_tenant(control, PLATFORM_TENANT_SLUG) is not None


def needs_platform_setup(control: Session, is_saas: bool) -> bool:
    """多账套部署且控制库还是空的：首次打开网页应显示「设置平台管理员」。"""
    return is_saas and not is_platform_ready(control)


def setup_platform_admin(control: Session, username: str, password: str, user_agent: str) -> Grant:
    """创建首个平台管理员并直接登录；已初始化过时 409。"""
    encoded = hash_password(password)  # 慢哈希放在锁外
    with _bootstrap_lock:
        if is_platform_ready(control):
            control.rollback()
            raise ConflictError(MSG_PLATFORM_READY)
        grant = _create_platform_admin(control, username, encoded, user_agent)
        _commit_once(control)
    return grant


def _create_platform_admin(
    control: Session, username: str, password_hash: str, user_agent: str
) -> Grant:
    """建号 → 标记平台管理员 → 开通平台运营账套 → 设为其管理员 → 签发会话。"""
    account = create_account(
        control, username, username, password_hash=password_hash, is_platform_admin=True
    )
    tenant = create_tenant(control, PLATFORM_TENANT_SLUG, PLATFORM_TENANT_NAME)
    membership = ensure_membership(control, account.id, tenant.id, role=ROLE_ADMIN)
    member = Member(account=account, membership=membership)
    return start_session(control, member, tenant, user_agent)


def _commit_once(control: Session) -> None:
    """跨进程抢跑兜底：用户名与账套 slug 都有唯一约束，写输的一方回滚并按 409 处理。"""
    try:
        control.commit()
    except IntegrityError as error:
        control.rollback()
        raise ConflictError(MSG_PLATFORM_READY) from error
