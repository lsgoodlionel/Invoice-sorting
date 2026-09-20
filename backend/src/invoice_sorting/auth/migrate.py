"""启动迁移（幂等）：确保内置管理员 admin 存在；旧版单一密码转为 admin 密码；清理无主会话。"""

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from invoice_sorting.db.models import AppSetting, AuthSession, User, now
from invoice_sorting.users.repository import (
    ADMIN_DISPLAY_NAME,
    ADMIN_USERNAME,
    UserRole,
    get_admin,
)

LEGACY_PASSWORD_KEY = "auth_password_hash"


def _legacy_password(db: Session) -> str | None:
    row = db.get(AppSetting, LEGACY_PASSWORD_KEY)
    return row.value if row is not None and row.value else None


def _create_admin(db: Session, password_hash: str | None) -> None:
    db.add(
        User(
            username=ADMIN_USERNAME,
            display_name=ADMIN_DISPLAY_NAME,
            role=str(UserRole.ADMIN),
            password_hash=password_hash,
            is_active=True,
            created_at=now(),
        )
    )


def migrate_users(db: Session, create_admin: bool = True) -> None:
    """create_admin=False 用于 SaaS 租户：成员由控制面开通，镜像不凭空多一行 admin。"""
    legacy = _legacy_password(db)
    db.execute(delete(AppSetting).where(AppSetting.key == LEGACY_PASSWORD_KEY))
    # 旧版会话不关联用户，全部失效（需重新登录）
    db.execute(delete(AuthSession).where(AuthSession.user_id.is_(None)))
    if create_admin and get_admin(db) is None:
        _create_admin(db, legacy)
    try:
        db.commit()
    except IntegrityError:  # 其他进程同时启动并已创建 admin
        db.rollback()
