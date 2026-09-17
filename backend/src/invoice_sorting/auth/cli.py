"""命令行：reset-password 清空登录密码与全部会话。"""

from invoice_sorting.auth.service import reset_credentials
from invoice_sorting.config import Settings
from invoice_sorting.db.session import create_db_engine, init_db, make_session_factory

RESET_DONE_MESSAGE = "已清除登录密码，请打开网页重新设置初始密码"


def reset_password(settings: Settings) -> None:
    settings.ensure_dirs()
    engine = create_db_engine(f"sqlite:///{settings.db_path}")
    try:
        init_db(engine)
        with make_session_factory(engine)() as db:
            reset_credentials(db)
            db.commit()
    finally:
        engine.dispose()
    print(RESET_DONE_MESSAGE)
