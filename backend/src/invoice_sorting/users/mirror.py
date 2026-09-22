"""租户内用户镜像（设计 2.2）：业务库 `app_user` 是控制面账号在本租户的投影。

- `User.id` 恒等于 `Account.id`，附件上传人、时间线操作人等既有外键继续可用。
- 同步 username / display_name / role / is_active，**不再使用业务库 password_hash**
  （列保留，回滚到旧版本仍可登录）。
- 同步时机：登录、切换账套、加入账套、成员增删改、租户业务库首次加载。
- 已删除账号的镜像行（is_deleted）保留原姓名；`app_user.username` 有唯一约束，
  有人重新使用这个用户名时，旧行的 username 改为 `原名~id` 让位（`~` 不是合法用户名字符，
  不会与真实用户名冲突）。只在同步时让位，因此老数据里已删除的行也同样适用。
"""

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from invoice_sorting.control.members import Member
from invoice_sorting.db.models import User, now

logger = logging.getLogger(__name__)

USERNAME_MAX = 32
DISPLAY_NAME_MAX = 32
RELEASED_MARK = "~"


def _apply(user: User, member: Member) -> None:
    user.username = member.account.username[:USERNAME_MAX]
    user.display_name = (member.account.display_name or member.account.username)[:DISPLAY_NAME_MAX]
    user.role = member.role
    user.is_active = member.is_active
    user.last_login_at = member.account.last_login_at
    # 账号仍在（例如移出后又被加回本账套）：镜像恢复为正常成员
    user.is_deleted = False
    user.deleted_at = None


def released_username(username: str, user_id: int) -> str:
    """已删除用户让出用户名后的占位名：`原名~id`，截断到列宽。"""
    tail = f"{RELEASED_MARK}{user_id}"
    return f"{username[: USERNAME_MAX - len(tail)]}{tail}"


def release_username(business: Session, username: str, owner_id: int) -> None:
    """同名的已删除镜像行让出用户名；未删除的同名行不动（仍按冲突处理）。"""
    holder = business.scalar(
        select(User).where(
            User.username == username, User.id != owner_id, User.is_deleted.is_(True)
        )
    )
    if holder is None:
        return
    holder.username = released_username(username, holder.id)
    business.flush()


def sync_member_mirror(business: Session, member: Member) -> User:
    """按控制面身份补齐/更新镜像行；返回业务库中的 User。"""
    release_username(business, member.account.username[:USERNAME_MAX], member.id)
    user = business.get(User, member.id)
    if user is None:
        user = User(id=member.id, created_at=member.account.created_at or now())
        business.add(user)
    _apply(user, member)
    business.flush()
    return user


def sync_members_mirror(business: Session, members: list[Member]) -> int:
    """按成员列表补齐镜像；单条失败（例如历史遗留的重名行）不影响其余成员。"""
    synced = 0
    for member in members:
        try:
            with business.begin_nested():
                sync_member_mirror(business, member)
            synced += 1
        except IntegrityError:
            logger.warning("用户镜像同步失败（用户名冲突）：%s", member.account.username)
    return synced
