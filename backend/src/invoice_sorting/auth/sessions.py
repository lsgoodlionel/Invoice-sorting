"""登录会话存储（控制库）：只存令牌 SHA-256；30 天有效，超过 1 小时未写入才续期。

会话记录**当前所选租户**（tenant_id）。校验时要求账号在目标租户内有启用中的成员关系：
子域名指定了别的租户而账号不是其成员时返回明确的 403，绝不放行。
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from invoice_sorting.auth.context import AuthUser
from invoice_sorting.control.members import Member, active_member
from invoice_sorting.control.models import Account, ControlAuthSession
from invoice_sorting.db.models import TZ, now

TOKEN_BYTES = 32
SESSION_LIFETIME = timedelta(days=30)
RENEW_INTERVAL = timedelta(hours=1)
USER_AGENT_MAX = 200

MSG_NOT_A_MEMBER = "当前账号不属于该账套，请联系管理员开通"


@dataclass(frozen=True)
class SessionCheck:
    is_valid: bool
    is_renewed: bool = False
    user: AuthUser | None = None
    # 明确的拒绝原因（例如不是该账套成员）；为空时按“请先登录”处理
    denial: str | None = None
    status_code: int = 401


INVALID = SessionCheck(is_valid=False)
FORBIDDEN = SessionCheck(is_valid=False, denial=MSG_NOT_A_MEMBER, status_code=403)


def member_user(member: Member) -> AuthUser:
    """租户内的身份快照：角色取自成员关系，而非账号本身。"""
    return AuthUser(
        id=member.account.id,
        username=member.account.username,
        display_name=member.account.display_name,
        role=member.role,
    )


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _aware(value: datetime) -> datetime:
    """SQLite 读回的时间不带时区（写入时为 Asia/Shanghai 墙钟时间）。"""
    return value if value.tzinfo is not None else value.replace(tzinfo=TZ)


def purge_expired(control: Session, at: datetime | None = None) -> None:
    deadline = at or now()
    control.execute(delete(ControlAuthSession).where(ControlAuthSession.expires_at <= deadline))


def create_session(
    control: Session,
    account_id: int,
    tenant_id: int | None,
    user_agent: str = "",
    at: datetime | None = None,
) -> str:
    current = at or now()
    token = secrets.token_urlsafe(TOKEN_BYTES)
    control.add(
        ControlAuthSession(
            token_hash=hash_token(token),
            account_id=account_id,
            tenant_id=tenant_id,
            created_at=current,
            last_seen_at=current,
            expires_at=current + SESSION_LIFETIME,
            user_agent=(user_agent or "")[:USER_AGENT_MAX],
        )
    )
    control.flush()
    return token


def find_session(control: Session, token: str | None) -> ControlAuthSession | None:
    """按令牌取未过期的会话行；过期行顺手删除。"""
    if not token:
        return None
    row = control.get(ControlAuthSession, hash_token(token))
    if row is None:
        return None
    if _aware(row.expires_at) <= now():
        control.delete(row)
        return None
    return row


def session_tenant_id(control: Session, token: str | None) -> int | None:
    """会话当前所选租户；用于在解析租户前写入请求状态。"""
    row = find_session(control, token)
    return row.tenant_id if row is not None else None


def set_session_tenant(control: Session, token: str | None, tenant_id: int) -> bool:
    """切换会话所选租户；调用方必须先校验成员关系。"""
    row = find_session(control, token)
    if row is None:
        return False
    row.tenant_id = tenant_id
    control.flush()
    return True


def _renewed(row: ControlAuthSession, user: AuthUser, current: datetime) -> SessionCheck:
    if current - _aware(row.last_seen_at) < RENEW_INTERVAL:
        return SessionCheck(is_valid=True, user=user)
    row.last_seen_at = current
    row.expires_at = current + SESSION_LIFETIME
    return SessionCheck(is_valid=True, is_renewed=True, user=user)


def validate_session(
    control: Session, token: str | None, tenant_id: int, at: datetime | None = None
) -> SessionCheck:
    """校验令牌、账号状态与目标租户成员关系。调用方负责提交。"""
    row = find_session(control, token)
    if row is None:
        return INVALID
    account = control.get(Account, row.account_id)
    if account is None or not account.is_active:
        delete_account_sessions(control, row.account_id)
        return INVALID
    member = active_member(control, account.id, tenant_id)
    if member is None:
        if row.tenant_id == tenant_id:
            delete_account_sessions(control, account.id)  # 本账套内已被停用
            return INVALID
        return FORBIDDEN  # 子域名指向了账号无权进入的账套
    return _renewed(row, member_user(member), at or now())


def delete_session(control: Session, token: str | None) -> None:
    if token:
        control.execute(
            delete(ControlAuthSession).where(ControlAuthSession.token_hash == hash_token(token))
        )


def delete_account_sessions(
    control: Session, account_id: int, keep_token: str | None = None
) -> None:
    """删除某账号的会话；keep_token 指定时保留该令牌（修改本人密码）。"""
    statement = delete(ControlAuthSession).where(ControlAuthSession.account_id == account_id)
    if keep_token:
        statement = statement.where(ControlAuthSession.token_hash != hash_token(keep_token))
    control.execute(statement)
