"""平台侧的成员管理：为**任意账套**添加/停用成员、重置密码、签发邀请码。

与租户内的「设置 → 用户管理」共用同一套业务规则（users/service.py），
区别只在于目标账套由平台管理员显式指定，而不是当前请求所在的账套。
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from invoice_sorting.auth.passwords import hash_password
from invoice_sorting.common.errors import AppError, ConflictError
from invoice_sorting.control.members import Member, find_member
from invoice_sorting.control.models import Invite, Membership, Tenant
from invoice_sorting.control.repository import create_account, find_account
from invoice_sorting.invites.service import create_invite
from invoice_sorting.platform_admin.schemas import InviteCreate, MemberCreate
from invoice_sorting.users.sync import sync_member_into_tenant

logger = logging.getLogger(__name__)

MSG_ALREADY_MEMBER = "该账号已在此账套中"
MSG_PASSWORD_REQUIRED = "新账号需要设置初始密码"


def add_member(control: Session, tenant: Tenant, body: MemberCreate) -> Member:
    """已存在的账号直接加入该账套（不改密码）；新账号需要初始密码。"""
    account = find_account(control, body.username)
    if account is None:
        account = _new_account(control, body)
    elif find_member(control, account.id, tenant.id) is not None:
        raise ConflictError(MSG_ALREADY_MEMBER)
    membership = Membership(
        account_id=account.id, tenant_id=tenant.id, role=str(body.role), is_active=True
    )
    control.add(membership)
    control.flush()
    return Member(account=account, membership=membership)


def _new_account(control: Session, body: MemberCreate):
    if not body.password:
        raise AppError(MSG_PASSWORD_REQUIRED, status_code=400)
    return create_account(
        control,
        body.username,
        body.display_name or body.username,
        password_hash=hash_password(body.password),
    )


def issue_invite(control: Session, tenant: Tenant, body: InviteCreate) -> Invite:
    """复用租户内的邀请码逻辑，只是账套由平台管理员指定。"""
    return create_invite(control, tenant.id, str(body.role), body.expires_on)


def mirror_member(app: Any, slug: str, member: Member) -> None:
    """把成员同步进该账套业务库的用户镜像。

    控制库的变更此时已经生效，镜像失败不应让整个操作失败：
    记录日志即可，账套下次加载或该成员下次登录时会自动补齐。
    """
    try:
        sync_member_into_tenant(app, slug, member)
    except Exception:
        logger.exception("账套 %s 的用户镜像同步失败", slug)
