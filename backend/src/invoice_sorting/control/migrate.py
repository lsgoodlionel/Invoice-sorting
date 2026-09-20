"""升级迁移（设计 8，幂等）：业务库的账号与会话搬到控制库。

- `app_user` → 控制库 `account` + `membership`，**保持 id 不变**，密码哈希原样搬。
- 业务库 `app_user` 保留为镜像（附件上传人等外键继续可用），本批不删 password_hash 列，
  因此回退到旧版本仍可运行。
- 业务库 `auth_session` 复制到控制库（原行不删），用户升级后无需重新登录。

可重复执行：已存在的账号、成员关系与会话都会跳过。
"""

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from invoice_sorting.control.models import Account, ControlAuthSession
from invoice_sorting.control.repository import (
    ensure_membership,
    find_account,
    find_membership,
    normalize_username,
)
from invoice_sorting.db.models import AuthSession, User

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MigrationReport:
    """本次迁移新增的行数；全为 0 表示无需迁移。"""

    accounts: int = 0
    memberships: int = 0
    sessions: int = 0

    @property
    def is_empty(self) -> bool:
        return not (self.accounts or self.memberships or self.sessions)


def migrate_tenant_accounts(
    control: Session, tenant_id: int, factory: sessionmaker[Session]
) -> MigrationReport:
    """把某租户业务库中的账号与会话迁到控制库。调用方负责提交控制库会话。"""
    with factory() as business:
        users = list(business.scalars(select(User).order_by(User.id)))
        sessions = list(business.scalars(select(AuthSession)))
    accounts, memberships = _migrate_users(control, tenant_id, users)
    moved = _migrate_sessions(control, tenant_id, sessions)
    report = MigrationReport(accounts=accounts, memberships=memberships, sessions=moved)
    if not report.is_empty:
        logger.info(
            "控制库迁移完成：账号 %s、成员 %s、会话 %s",
            report.accounts,
            report.memberships,
            report.sessions,
        )
    return report


def _migrate_users(control: Session, tenant_id: int, users: list[User]) -> tuple[int, int]:
    created_accounts = 0
    created_memberships = 0
    for user in users:
        account, is_new_account = _upsert_account(control, user)
        created_accounts += int(is_new_account)
        if find_membership(control, account.id, tenant_id) is not None:
            continue
        ensure_membership(control, account.id, tenant_id, role=user.role, is_active=user.is_active)
        created_memberships += 1
    return created_accounts, created_memberships


def _upsert_account(control: Session, user: User) -> tuple[Account, bool]:
    """按 id 对齐控制库账号；已存在（含同名不同 id）时返回既有账号。"""
    by_id = control.get(Account, user.id)
    if by_id is not None:
        return by_id, False
    username = normalize_username(user.username)
    by_name = find_account(control, username)
    if by_name is not None:
        logger.warning(
            "控制库已存在同名账号 %s（id=%s），业务库 id=%s 未能对齐", username, by_name.id, user.id
        )
        return by_name, False
    account = Account(
        id=user.id,
        username=username,
        display_name=user.display_name,
        password_hash=user.password_hash,
        is_platform_admin=False,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )
    control.add(account)
    control.flush()
    return account, True


def _migrate_sessions(control: Session, tenant_id: int, rows: list[AuthSession]) -> int:
    moved = 0
    for row in rows:
        if row.user_id is None or control.get(Account, row.user_id) is None:
            continue  # 无主会话（旧版遗留）不迁移，登录后自然重建
        if control.get(ControlAuthSession, row.token_hash) is not None:
            continue
        control.add(
            ControlAuthSession(
                token_hash=row.token_hash,
                account_id=row.user_id,
                tenant_id=tenant_id,
                created_at=row.created_at,
                last_seen_at=row.last_seen_at,
                expires_at=row.expires_at,
                user_agent=row.user_agent,
            )
        )
        moved += 1
    control.flush()
    return moved
