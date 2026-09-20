"""数据库引擎与会话。"""

from sqlalchemy import Column, Engine, MetaData, create_engine, event, inspect
from sqlalchemy.orm import Session, sessionmaker

from invoice_sorting.db.models import Base


def create_db_engine(db_url: str) -> Engine:
    engine = create_engine(db_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record) -> None:  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def init_db(engine: Engine, metadata: MetaData | None = None) -> None:
    """建表并补列；metadata 省略时为业务库，控制库传入自己的 metadata。"""
    target = metadata if metadata is not None else Base.metadata
    target.create_all(engine)
    add_missing_columns(engine, target)


def add_missing_columns(engine: Engine, metadata: MetaData | None = None) -> None:
    """轻量迁移：为已有表补齐模型中新增的列（SQLite 仅支持追加列）。"""
    target = metadata if metadata is not None else Base.metadata
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in target.sorted_tables:
            existing = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name not in existing:
                    conn.exec_driver_sql(_add_column_sql(engine, table.name, column))


def _add_column_sql(engine: Engine, table: str, column: Column) -> str:
    column_type = column.type.compile(dialect=engine.dialect)
    prefix = f'ALTER TABLE "{table}" ADD COLUMN "{column.name}" {column_type}'
    default = column.default.arg if column.default is not None else None
    if isinstance(default, bool):
        default = int(default)
    if isinstance(default, str):
        escaped = default.replace("'", "''")
        return f"{prefix} NOT NULL DEFAULT '{escaped}'"
    if isinstance(default, int):
        return f"{prefix} NOT NULL DEFAULT {default}"
    return prefix


def ensure_transaction(session: Session) -> None:
    """pysqlite 在首条写语句前不会 BEGIN，此时 SAVEPOINT 的 RELEASE 会直接提交。

    使用 session.begin_nested() 做“单条失败只回滚该条”之前先调用，保证外层事务真实存在。
    """
    driver = session.connection().connection.driver_connection
    if driver is not None and not driver.in_transaction:
        driver.execute("BEGIN")


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
