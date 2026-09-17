"""认证业务：初始密码设置、登录校验、修改密码、重置。"""

import threading

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from invoice_sorting.auth.passwords import hash_password, verify_password
from invoice_sorting.auth.sessions import (
    create_session,
    delete_all_sessions,
    delete_other_sessions,
    purge_expired,
)
from invoice_sorting.common.errors import AppError, ConflictError
from invoice_sorting.db.models import AppSetting

PASSWORD_KEY = "auth_password_hash"
MSG_NEED_SETUP = "请先设置初始密码"
MSG_LOGIN_REQUIRED = "请先登录"
MSG_ALREADY_SET = "已设置过初始密码，请直接登录"
MSG_WRONG_PASSWORD = "密码错误"
MSG_WRONG_CURRENT = "当前密码错误"

# 同进程内串行化初始密码设置；数据库主键约束兜底跨进程并发
_setup_lock = threading.Lock()


def get_password_hash(db: Session) -> str | None:
    row = db.get(AppSetting, PASSWORD_KEY)
    return row.value if row is not None and row.value else None


def is_password_set(db: Session) -> bool:
    return get_password_hash(db) is not None


def _store_hash(db: Session, encoded: str) -> None:
    row = db.get(AppSetting, PASSWORD_KEY)
    if row is None:
        db.add(AppSetting(key=PASSWORD_KEY, value=encoded))
    else:
        row.value = encoded
    db.flush()


def setup_initial_password(db: Session, password: str, user_agent: str) -> str:
    """设置初始密码并创建会话，返回明文令牌。已设置过时 409。检查与写入在同一事务内提交。"""
    encoded = hash_password(password)  # 慢哈希放在锁外
    with _setup_lock:
        if is_password_set(db):
            raise ConflictError(MSG_ALREADY_SET)
        try:
            _store_hash(db, encoded)
            purge_expired(db)
            token = create_session(db, user_agent)
            db.commit()
        except IntegrityError as exc:  # 其他进程抢先写入了密码
            db.rollback()
            raise ConflictError(MSG_ALREADY_SET) from exc
    return token


def require_password_hash(db: Session) -> str:
    encoded = get_password_hash(db)
    if encoded is None:
        raise ConflictError(MSG_NEED_SETUP)
    return encoded


def login_with_password(db: Session, password: str, user_agent: str) -> str | None:
    """密码正确返回新会话令牌；错误返回 None（由调用方计入失败次数）。"""
    encoded = require_password_hash(db)
    if not verify_password(password, encoded):
        return None
    purge_expired(db)
    return create_session(db, user_agent)


def change_password(db: Session, current: str, new: str, keep_token: str | None) -> None:
    encoded = require_password_hash(db)
    if not verify_password(current, encoded):
        raise AppError(MSG_WRONG_CURRENT, status_code=400)
    _store_hash(db, hash_password(new))
    delete_other_sessions(db, keep_token)


def reset_credentials(db: Session) -> None:
    """清空密码与全部会话（忘记密码时由服务器命令行调用）。"""
    db.execute(delete(AppSetting).where(AppSetting.key == PASSWORD_KEY))
    delete_all_sessions(db)
