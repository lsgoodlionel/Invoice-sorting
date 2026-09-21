"""控制库引擎与会话工厂：与业务库共用建连/建表工具，但指向 control.db。"""

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from invoice_sorting.config import Settings
from invoice_sorting.control import signup_models  # noqa: F401 - 登记注册申请相关表
from invoice_sorting.control.models import ControlBase
from invoice_sorting.db.session import create_db_engine, init_db, make_session_factory


def create_control_engine(settings: Settings) -> Engine:
    """控制库位于 data_dir 根目录；两种部署形态都存在。"""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return create_db_engine(f"sqlite:///{settings.control_db_path}")


def init_control_db(engine: Engine) -> None:
    """建表并补列（沿用业务库的轻量迁移策略），可重复执行。"""
    init_db(engine, ControlBase.metadata)


def make_control_session_factory(engine: Engine) -> sessionmaker[Session]:
    return make_session_factory(engine)
