"""业务库中的用户镜像查询：按用户名查找、内置管理员。

登录与角色以控制库为准（control/members.py），这里只服务于镜像本身
（启动迁移、上传人/操作人展示）。
"""

from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.control.members import BUILTIN_ADMIN_USERNAME
from invoice_sorting.db.models import User

ADMIN_USERNAME = BUILTIN_ADMIN_USERNAME
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
