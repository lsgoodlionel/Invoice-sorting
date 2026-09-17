"""数据库引擎与会话。"""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Column, Engine, create_engine, event, inspect
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


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
    add_missing_columns(engine)


def add_missing_columns(engine: Engine) -> None:
    """轻量迁移：为已有表补齐模型中新增的列（SQLite 仅支持追加列）。"""
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
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


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_session(request: Request) -> Iterator[Session]:
    """FastAPI 依赖：每个请求一个会话，异常时回滚。"""
    factory: sessionmaker[Session] = request.app.state.session_factory
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
