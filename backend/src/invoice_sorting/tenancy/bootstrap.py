"""业务库首次加载：建目录、建表补列、写入种子与启动迁移。

流程与改造前 main.create_app 中的启动步骤完全一致，单租户升级后行为不变。
"""

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from invoice_sorting.attachments.file_keys import backfill_file_keys
from invoice_sorting.auth.migrate import migrate_users
from invoice_sorting.config import Settings
from invoice_sorting.db.seed import (
    reset_polluted_memory,
    seed_defaults,
    sync_default_keywords,
    sync_default_rules,
)
from invoice_sorting.db.session import create_db_engine, init_db, make_session_factory


def open_business_db(settings: Settings) -> tuple[Engine, sessionmaker[Session]]:
    """按配置打开（必要时创建）业务库，返回引擎与会话工厂。"""
    settings.ensure_dirs()
    engine = create_db_engine(f"sqlite:///{settings.db_path}")
    try:
        init_db(engine)
        factory = make_session_factory(engine)
        with factory() as session:
            _seed(session)
    except Exception:
        engine.dispose()  # 初始化失败时不泄漏连接池
        raise
    return engine, factory


def _seed(session: Session) -> None:
    seed_defaults(session)
    sync_default_keywords(session)
    sync_default_rules(session)
    reset_polluted_memory(session)
    backfill_file_keys(session)
    migrate_users(session)
