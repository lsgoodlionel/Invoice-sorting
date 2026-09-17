"""认证业务：admin 初始密码、用户名密码登录、修改本人密码、命令行重置。"""

import threading
from dataclasses import dataclass
from functools import cache

from sqlalchemy import update
from sqlalchemy.orm import Session

from invoice_sorting.auth.context import AuthUser
from invoice_sorting.auth.passwords import hash_password, verify_password
from invoice_sorting.auth.sessions import create_session, delete_user_sessions, purge_expired
from invoice_sorting.common.errors import AppError, ConflictError, NotFoundError
from invoice_sorting.db.models import User, now
from invoice_sorting.users.repository import ADMIN_USERNAME, find_user, get_admin

MSG_NEED_SETUP = "请先设置初始密码"
MSG_LOGIN_REQUIRED = "请先登录"
MSG_ALREADY_SET = "已设置过初始密码，请直接登录"
MSG_WRONG_CREDENTIALS = "用户名或密码错误"
MSG_WRONG_CURRENT = "当前密码错误"

# 同进程内串行化初始密码设置；条件 UPDATE（仅当密码为空）兜底跨进程并发
_setup_lock = threading.Lock()


@dataclass(frozen=True)
class Grant:
    """登录成功：明文会话令牌与当前用户。"""

    token: str
    user: AuthUser


@cache
def _dummy_hash() -> str:
    """用户不存在或未设置密码时也做一次同等代价的哈希校验，避免计时差异泄露用户名。"""
    return hash_password("invoice-sorting-dummy-password")


def is_password_set(db: Session) -> bool:
    admin = get_admin(db)
    return admin is not None and admin.password_hash is not None


def _start_session(db: Session, user: User, user_agent: str) -> Grant:
    user.last_login_at = now()
    purge_expired(db)
    token = create_session(db, user.id, user_agent)
    return Grant(token=token, user=AuthUser.from_model(user))


def setup_initial_password(db: Session, password: str, user_agent: str) -> Grant:
    """为 admin 设置初始密码并以 admin 登录。已设置过时 409。检查与写入在同一事务内提交。"""
    encoded = hash_password(password)  # 慢哈希放在锁外
    with _setup_lock:
        statement = (
            update(User)
            .where(User.username == ADMIN_USERNAME, User.password_hash.is_(None))
            .values(password_hash=encoded)
            .execution_options(synchronize_session=False)
        )
        if db.execute(statement).rowcount != 1:
            db.rollback()
            raise ConflictError(MSG_ALREADY_SET)
        admin = get_admin(db)
        db.refresh(admin)
        grant = _start_session(db, admin, user_agent)
        db.commit()
    return grant


def _require_setup(db: Session) -> None:
    if not is_password_set(db):
        raise ConflictError(MSG_NEED_SETUP)


def authenticate(db: Session, username: str, password: str) -> User | None:
    """用户名不存在、未设置密码、密码错误或已停用均返回 None（统一对外错误）。"""
    user = find_user(db, username)
    encoded = user.password_hash if user is not None else None
    is_match = verify_password(password, encoded or _dummy_hash())
    if user is None or encoded is None or not is_match or not user.is_active:
        return None
    return user


def login_with_password(db: Session, username: str, password: str, user_agent: str) -> Grant | None:
    """凭据正确返回会话；错误返回 None（由调用方计入失败次数）。admin 未设置密码时 409。"""
    _require_setup(db)
    user = authenticate(db, username, password)
    return _start_session(db, user, user_agent) if user is not None else None


def change_password(
    db: Session, user_id: int, current: str, new: str, keep_token: str | None
) -> None:
    """修改本人密码；本人其他会话失效，当前会话保留。"""
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("用户")
    if not verify_password(current, user.password_hash):
        raise AppError(MSG_WRONG_CURRENT, status_code=400)
    user.password_hash = hash_password(new)
    delete_user_sessions(db, user.id, keep_token)
    db.flush()


def reset_credentials(db: Session, username: str = ADMIN_USERNAME) -> bool:
    """清除指定用户（默认 admin）的密码与全部会话；用户不存在返回 False。"""
    user = find_user(db, username)
    if user is None:
        return False
    user.password_hash = None
    delete_user_sessions(db, user.id)
    db.flush()
    return True
