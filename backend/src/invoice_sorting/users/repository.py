"""用户数据访问：按用户名查找、内置管理员、合格管理员计数。"""

from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from invoice_sorting.db.models import User

ADMIN_USERNAME = "admin"
ADMIN_DISPLAY_NAME = "管理员"


class UserRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


def normalize_username(username: str) -> str:
    return username.strip().lower()


def find_user(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == normalize_username(username)))


def get_admin(db: Session) -> User | None:
    return find_user(db, ADMIN_USERNAME)


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.created_at, User.id)))


def count_ready_admins(db: Session, exclude_id: int | None = None) -> int:
    """启用中且已设置密码的管理员数量（可排除某个用户，用于预判修改后的状态）。"""
    query = select(func.count(User.id)).where(
        User.role == UserRole.ADMIN, User.is_active.is_(True), User.password_hash.is_not(None)
    )
    if exclude_id is not None:
        query = query.where(User.id != exclude_id)
    return db.scalar(query) or 0
