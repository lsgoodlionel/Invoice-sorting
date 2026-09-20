"""命令行：`invoice-sorting grant-platform-admin --username x`。

首个平台管理员必须能**离线**产生：本命令只读写本机控制库（control.db），不联网、
不依赖前端。它会（按需）建号、标记 `is_platform_admin`，并确保该账号至少属于一个账套，
否则登录时会因为「尚未加入任何账套」而被拒绝。

多租户部署且该账号还没有任何账套时，自动开通一个运营账套（platform / 平台运营）；
单账套部署直接挂到 default 账套。

注意：**首次**也可以直接在网页上设置（第一次打开页面即可创建首个平台管理员，见
platform_admin/bootstrap.py）；本命令主要用于忘记密码、批量运维或没有浏览器的场景。
"""

import getpass
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.auth.passwords import hash_password
from invoice_sorting.auth.schemas import PASSWORD_MIN
from invoice_sorting.common.errors import AppError
from invoice_sorting.config import DEFAULT_TENANT_NAME, DEFAULT_TENANT_SLUG, Settings
from invoice_sorting.control.database import (
    create_control_engine,
    init_control_db,
    make_control_session_factory,
)
from invoice_sorting.control.models import ROLE_ADMIN, Account, Membership, Tenant
from invoice_sorting.control.repository import (
    create_account,
    ensure_membership,
    ensure_tenant,
    find_account,
    normalize_username,
)
from invoice_sorting.platform_admin.bootstrap import PLATFORM_TENANT_NAME, PLATFORM_TENANT_SLUG

PROMPT = "请输入该账号的初始密码："

MSG_PASSWORD_REQUIRED = f"新账号需要初始密码（至少 {PASSWORD_MIN} 位），请用 --password 提供"
MSG_PASSWORD_TOO_SHORT = f"密码至少需要 {PASSWORD_MIN} 位"
MSG_USERNAME_REQUIRED = "请用 --username 指定账号"
EXIT_INVALID = 1


def _ask_password(password: str | None, is_new_account: bool) -> str | None:
    """新账号必须有密码；命令行没给就交互式询问（不回显），非交互环境直接报错。"""
    secret = password or ""
    if not secret and is_new_account and sys.stdin.isatty():
        secret = getpass.getpass(PROMPT)
    if not secret:
        if is_new_account:
            raise AppError(MSG_PASSWORD_REQUIRED)
        return None
    if len(secret) < PASSWORD_MIN:
        raise AppError(MSG_PASSWORD_TOO_SHORT)
    return secret


def _first_membership(control: Session, account_id: int) -> Membership | None:
    return control.scalar(
        select(Membership).where(Membership.account_id == account_id).order_by(Membership.id)
    )


def _home_tenant(control: Session, settings: Settings, account: Account) -> Tenant:
    """平台管理员的归属账套：已有账套就沿用，否则按部署形态开通一个。"""
    existing = _first_membership(control, account.id)
    tenant = control.get(Tenant, existing.tenant_id) if existing is not None else None
    if tenant is not None:
        return tenant
    if settings.is_saas:
        return ensure_tenant(control, PLATFORM_TENANT_SLUG, PLATFORM_TENANT_NAME)
    return ensure_tenant(control, DEFAULT_TENANT_SLUG, DEFAULT_TENANT_NAME)


def _upsert_account(control: Session, username: str, password: str | None, display: str) -> Account:
    account = find_account(control, username)
    if account is None:
        return create_account(
            control,
            username,
            display or username,
            password_hash=hash_password(password or ""),
            is_platform_admin=True,
        )
    account.is_platform_admin = True
    account.is_active = True
    if password:
        account.password_hash = hash_password(password)
    if display:
        account.display_name = display
    control.flush()
    return account


def _promote(membership: Membership) -> Membership:
    """平台管理员在归属账套内也按管理员对待（否则进不了账套内的设置页）。"""
    membership.role = ROLE_ADMIN
    membership.is_active = True
    return membership


def grant_platform_admin(
    settings: Settings, username: str, password: str | None = None, display_name: str = ""
) -> str:
    """标记平台管理员并确保其归属账套；返回给运维看的中文结果说明。"""
    name = normalize_username(username)
    engine = create_control_engine(settings)
    try:
        init_control_db(engine)
        with make_control_session_factory(engine)() as control:
            secret = _ask_password(password, find_account(control, name) is None)
            account = _upsert_account(control, name, secret, display_name)
            tenant = _home_tenant(control, settings, account)
            _promote(ensure_membership(control, account.id, tenant.id, role=ROLE_ADMIN))
            summary = _summary(account, tenant)
            control.commit()
            return summary
    finally:
        engine.dispose()


def _summary(account: Account, tenant: Tenant) -> str:
    return (
        f"已将 {account.username} 设为平台管理员，"
        f"归属账套：{tenant.name}（{tenant.slug}）。"
        "现在可用该账号登录，并在左侧导航进入「平台」。"
    )


def run_grant(
    settings: Settings, username: str | None, password: str | None = None, display: str = ""
) -> None:
    """命令行入口：参数不合法时给出中文提示并以非零状态退出。"""
    if not (username or "").strip():
        print(MSG_USERNAME_REQUIRED, file=sys.stderr)
        raise SystemExit(EXIT_INVALID)
    try:
        print(grant_platform_admin(settings, username, password, display))
    except AppError as error:
        print(error.message, file=sys.stderr)
        raise SystemExit(EXIT_INVALID) from error
