"""租户内用户镜像（设计 2.2）：业务库 `app_user` 是控制面账号在本租户的投影。

- `User.id` 恒等于 `Account.id`，附件上传人、时间线操作人等既有外键继续可用。
- 同步 username / display_name / role / is_active，**不再使用业务库 password_hash**
  （列保留，回滚到旧版本仍可登录）。
- 同步时机：登录、切换账套、加入账套、成员增删改、租户业务库首次加载。
"""

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from invoice_sorting.control.members import Member
from invoice_sorting.db.models import User, now

logger = logging.getLogger(__name__)

USERNAME_MAX = 32
DISPLAY_NAME_MAX = 32


def _apply(user: User, member: Member) -> None:
    user.username = member.account.username[:USERNAME_MAX]
    user.display_name = (member.account.display_name or member.account.username)[:DISPLAY_NAME_MAX]
    user.role = member.role
    user.is_active = member.is_active
    user.last_login_at = member.account.last_login_at


def sync_member_mirror(business: Session, member: Member) -> User:
    """按控制面身份补齐/更新镜像行；返回业务库中的 User。"""
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
