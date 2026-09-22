"""导出时收集登录账号（账本搬迁设计 2.1）：仅单账套部署，SaaS 的账号是平台共用的，不随账套走。"""

from sqlalchemy.orm import Session, sessionmaker

from invoice_sorting.config import Settings
from invoice_sorting.control.members import Member, list_members
from invoice_sorting.control.repository import find_tenant
from invoice_sorting.migration.accounts_file import SOURCES, AccountRecord, AccountsFile


def collect_accounts(
    control_factory: sessionmaker[Session], settings: Settings, slug: str
) -> AccountsFile | None:
    """该账套全部成员的账号快照；SaaS 部署或账套尚未登记（没有成员）时返回 None。"""
    if settings.is_saas:
        return None
    with control_factory() as control:
        tenant = find_tenant(control, slug)
        members = list_members(control, tenant.id) if tenant is not None else []
        records = tuple(sorted((_record(member) for member in members), key=lambda r: r.id))
    if not records:
        return None
    return AccountsFile(tenant=slug, accounts=records)


def _record(member: Member) -> AccountRecord:
    account = member.account
    return AccountRecord(
        id=account.id,
        username=account.username,
        display_name=account.display_name or account.username,
        role=member.role,
        is_active=member.is_active,
        source=account.source if account.source in SOURCES else "",
        password_hash=account.password_hash,
    )
