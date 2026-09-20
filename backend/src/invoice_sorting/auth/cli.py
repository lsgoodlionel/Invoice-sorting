"""命令行：reset-password 清除 admin（或 --user 指定用户）的密码与其全部会话。"""

import sys

from invoice_sorting.auth.migrate import migrate_users
from invoice_sorting.auth.service import reset_credentials
from invoice_sorting.config import Settings
from invoice_sorting.db.session import create_db_engine, init_db, make_session_factory
from invoice_sorting.users.repository import ADMIN_USERNAME, normalize_username

RESET_DONE_MESSAGE = "已清除 admin 登录密码，请打开网页重新设置初始密码"
MSG_SAAS_UNSUPPORTED = "多租户部署无法用命令行重置密码，请在平台运营后台操作"
EXIT_USER_NOT_FOUND = 1
EXIT_SAAS_UNSUPPORTED = 2


def _reset(settings: Settings, username: str) -> bool:
    settings.ensure_dirs()
    engine = create_db_engine(f"sqlite:///{settings.db_path}")
    try:
        init_db(engine)
        with make_session_factory(engine)() as db:
            migrate_users(db)
            is_found = reset_credentials(db, username)
            db.commit()
    finally:
        engine.dispose()
    return is_found


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
