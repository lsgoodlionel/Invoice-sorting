"""镜像同步的应用层入口：把控制面成员写进对应租户的业务库。

两种时机：
- 单个成员（登录、切换账套、加入账套、成员增删改）；
- 整个租户（业务库首次加载时按 membership 补齐，见 main.create_app 的 on_open）。
"""

from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from invoice_sorting.control.members import Member, list_members
from invoice_sorting.control.repository import find_tenant
from invoice_sorting.tenancy.deps import load_tenant
from invoice_sorting.tenancy.runtime import TenantContext
from invoice_sorting.users.mirror import sync_member_mirror, sync_members_mirror


def sync_member_into_tenant(app: Any, slug: str, member: Member) -> None:
    """按 slug 打开租户业务库并同步这一个成员的镜像。"""
    context = load_tenant(app, slug)
    with context.session_factory() as business:
        sync_member_mirror(business, member)
        business.commit()


def sync_member_into_session(business: Session, member: Member) -> None:
    """已经持有业务库会话时的同步入口（由调用方提交）。"""
    sync_member_mirror(business, member)


def sync_tenant_mirror(control_factory: sessionmaker[Session], context: TenantContext) -> None:
    """租户业务库首次加载：按控制库中的 membership 补齐镜像。"""
    with control_factory() as control:
        tenant = find_tenant(control, context.slug)
        members = list_members(control, tenant.id) if tenant is not None else []
    if not members:
        return
    with context.session_factory() as business:
        sync_members_mirror(business, members)
        business.commit()
