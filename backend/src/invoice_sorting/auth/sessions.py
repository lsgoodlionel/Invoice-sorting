"""登录会话存储：库中只存令牌 SHA-256；会话关联用户；30 天有效，超过 1 小时未写入才续期。"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from invoice_sorting.auth.context import AuthUser
from invoice_sorting.db.models import TZ, AuthSession, User, now

TOKEN_BYTES = 32
SESSION_LIFETIME = timedelta(days=30)
RENEW_INTERVAL = timedelta(hours=1)
USER_AGENT_MAX = 200


@dataclass(frozen=True)
class SessionCheck:
    is_valid: bool
    is_renewed: bool = False
    user: AuthUser | None = None


INVALID = SessionCheck(is_valid=False)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    """SQLite 读回的时间不带时区（写入时为 Asia/Shanghai 墙钟时间）。"""
    return value if value.tzinfo is not None else value.replace(tzinfo=TZ)


def purge_expired(db: Session, at: datetime | None = None) -> None:
    db.execute(delete(AuthSession).where(AuthSession.expires_at <= (at or now())))


def create_session(
    db: Session, user_id: int, user_agent: str = "", at: datetime | None = None
) -> str:
    current = at or now()
    token = secrets.token_urlsafe(TOKEN_BYTES)
    db.add(
        AuthSession(
            token_hash=hash_token(token),
            user_id=user_id,
            created_at=current,
            last_seen_at=current,
            expires_at=current + SESSION_LIFETIME,
            user_agent=(user_agent or "")[:USER_AGENT_MAX],
        )
    )
    db.flush()
    return token


def _session_user(db: Session, row: AuthSession) -> User | None:
    """会话对应的启用中用户；用户缺失或已停用时删除该用户的全部会话。"""
    user = db.get(User, row.user_id) if row.user_id is not None else None
    if user is not None and user.is_active:
        return user
    if row.user_id is None:
        db.delete(row)
    else:
        delete_user_sessions(db, row.user_id)
    return None


def validate_session(db: Session, token: str | None, at: datetime | None = None) -> SessionCheck:
    """校验令牌与所属用户；有效且距上次写入超过续期间隔时顺延有效期。调用方负责提交。"""
    if not token:
        return INVALID
    current = at or now()
    row = db.get(AuthSession, hash_token(token))
    if row is None:
        return INVALID
    if _aware(row.expires_at) <= current:
        db.delete(row)
        return INVALID
    user = _session_user(db, row)
    if user is None:
        return INVALID
    snapshot = AuthUser.from_model(user)
    if current - _aware(row.last_seen_at) < RENEW_INTERVAL:
        return SessionCheck(is_valid=True, user=snapshot)
    row.last_seen_at = current
    row.expires_at = current + SESSION_LIFETIME
    return SessionCheck(is_valid=True, is_renewed=True, user=snapshot)


def delete_session(db: Session, token: str | None) -> None:
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(token)))


def delete_user_sessions(db: Session, user_id: int, keep_token: str | None = None) -> None:
    """删除某用户的会话；keep_token 指定时保留该令牌对应的会话（修改本人密码）。"""
    statement = delete(AuthSession).where(AuthSession.user_id == user_id)
    if keep_token:
        statement = statement.where(AuthSession.token_hash != hash_token(keep_token))
    db.execute(statement)
