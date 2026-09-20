"""命令行：reset-password 清除 admin（或 --user 指定用户）的密码与其全部会话。

密码已统一存放在控制库，因此这里先确保老部署的账号已迁移过去，再清除。
"""

import sys

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from invoice_sorting.auth.migrate import migrate_users
from invoice_sorting.auth.service import reset_credentials
from invoice_sorting.config import DEFAULT_TENANT_NAME, DEFAULT_TENANT_SLUG, Settings
from invoice_sorting.control.database import (
    create_control_engine,
    init_control_db,
    make_control_session_factory,
)
from invoice_sorting.control.migrate import migrate_tenant_accounts
from invoice_sorting.control.repository import ensure_tenant
from invoice_sorting.db.session import create_db_engine, init_db, make_session_factory
from invoice_sorting.users.repository import ADMIN_USERNAME, normalize_username

RESET_DONE_MESSAGE = "已清除 admin 登录密码，请打开网页重新设置初始密码"
MSG_SAAS_UNSUPPORTED = "多租户部署无法用命令行重置密码，请在平台运营后台操作"
EXIT_USER_NOT_FOUND = 1
EXIT_SAAS_UNSUPPORTED = 2


def _open_business(settings: Settings) -> tuple[Engine, sessionmaker[Session]]:
    settings.ensure_dirs()
    engine = create_db_engine(f"sqlite:///{settings.db_path}")
    init_db(engine)
    factory = make_session_factory(engine)
    with factory() as db:
        migrate_users(db)
    return engine, factory


def _reset_in_control(settings: Settings, factory: sessionmaker[Session], username: str) -> bool:
    engine = create_control_engine(settings)
    try:
        init_control_db(engine)
        with make_control_session_factory(engine)() as control:
            tenant = ensure_tenant(control, DEFAULT_TENANT_SLUG, DEFAULT_TENANT_NAME)
            control.commit()
            migrate_tenant_accounts(control, tenant.id, factory)
            is_found = reset_credentials(control, username)
            control.commit()
    finally:
        engine.dispose()
    return is_found


def _reset(settings: Settings, username: str) -> bool:
    business, factory = _open_business(settings)
    try:
        return _reset_in_control(settings, factory, username)
    finally:
        business.dispose()


def reset_password(settings: Settings, username: str | None = None) -> None:
    # 多租户模式下 data_dir 根目录没有业务库，不能默默建一个空库
    if settings.is_saas:
        print(MSG_SAAS_UNSUPPORTED, file=sys.stderr)
        raise SystemExit(EXIT_SAAS_UNSUPPORTED)
    name = normalize_username(username or ADMIN_USERNAME)
    if not _reset(settings, name):
        print(f"用户不存在：{name}", file=sys.stderr)
        raise SystemExit(EXIT_USER_NOT_FOUND)
    if name == ADMIN_USERNAME:
        print(RESET_DONE_MESSAGE)
    else:
        print(f"已清除用户 {name} 的密码与登录会话，请管理员在网页中重新设置密码")
