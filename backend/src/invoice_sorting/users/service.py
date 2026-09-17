"""用户管理业务：创建、修改（姓名/角色/启用）、管理员重置密码。

约束：不能停用自己或把自己改为普通用户；系统至少保留一名启用中且已设置密码的管理员；
停用或重置密码后该用户全部会话失效。
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from invoice_sorting.auth.context import AuthUser
from invoice_sorting.auth.passwords import hash_password
from invoice_sorting.auth.sessions import delete_user_sessions
from invoice_sorting.common.errors import AppError, ConflictError, NotFoundError
from invoice_sorting.db.models import User, now
from invoice_sorting.users.repository import UserRole, count_ready_admins, find_user
from invoice_sorting.users.schemas import UserCreate, UserUpdate

MSG_USERNAME_TAKEN = "用户名已存在"
MSG_CANNOT_DEACTIVATE_SELF = "不能停用自己"
MSG_CANNOT_DEMOTE_SELF = "不能把自己改为普通用户"
MSG_LAST_ADMIN = "系统必须至少保留一名启用中且已设置密码的管理员"


def get_user_or_404(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("用户")
    return user


def create_user(db: Session, body: UserCreate) -> User:
    if find_user(db, body.username) is not None:
        raise ConflictError(MSG_USERNAME_TAKEN)
    user = User(
        username=body.username,
        display_name=body.display_name or body.username,
        role=str(body.role),
        password_hash=hash_password(body.password),
        is_active=True,
        created_at=now(),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:  # 并发创建同名用户
        db.rollback()
        raise ConflictError(MSG_USERNAME_TAKEN) from exc
    return user


def _check_self_change(actor: AuthUser | None, user: User, body: UserUpdate) -> None:
    if actor is None or actor.id != user.id:
        return
    if body.is_active is False:
        raise AppError(MSG_CANNOT_DEACTIVATE_SELF)
    if body.role == UserRole.MEMBER:
        raise AppError(MSG_CANNOT_DEMOTE_SELF)


def _is_ready_admin(role: str, is_active: bool, user: User) -> bool:
    return role == UserRole.ADMIN and is_active and user.password_hash is not None


def _check_admin_remains(db: Session, user: User, body: UserUpdate) -> None:
    """仅当本次修改让该用户失去“启用中且有密码的管理员”资格时，检查是否还有其他人。"""
    role = body.role if body.role is not None else user.role
    is_active = body.is_active if body.is_active is not None else bool(user.is_active)
    is_ready_before = _is_ready_admin(user.role, bool(user.is_active), user)
    if not is_ready_before or _is_ready_admin(role, is_active, user):
        return
    if count_ready_admins(db, exclude_id=user.id) == 0:
        raise AppError(MSG_LAST_ADMIN)


def update_user(db: Session, actor: AuthUser | None, user: User, body: UserUpdate) -> User:
    _check_self_change(actor, user, body)
    _check_admin_remains(db, user, body)
    was_active = bool(user.is_active)
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.role is not None:
        user.role = str(body.role)
    if body.is_active is not None:
        user.is_active = body.is_active
    if was_active and not user.is_active:
        delete_user_sessions(db, user.id)
    db.flush()
    return user


def reset_user_password(db: Session, user: User, password: str) -> None:
    user.password_hash = hash_password(password)
    delete_user_sessions(db, user.id)
    db.flush()
