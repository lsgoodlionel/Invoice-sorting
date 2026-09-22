"""账号恢复执行（账本搬迁设计 3.1）：单账套整套覆盖时，把包内 accounts.json 写回控制库。

- `preflight`：解包前只读检查，恢复后没有可用管理员就中止（此时未写入任何数据）；
- `restore_accounts`：解包后在**一个控制库事务**里完成 id 对齐、账号与成员关系写入、会话失效，
  提交前再核对一次“至少一个可用管理员”，任何一步失败整体回滚；
- id 对齐会同步改写控制库里所有引用 `account.id` 的外键列（按元数据自动发现），
  先把要调整的 id 挪到负数暂存位再落到目标位，避免交换时撞主键；外键检查推迟到提交时。
日志只记账号个数，绝不打印密码哈希。
"""

import logging
import sqlite3
from collections.abc import Iterable, Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Column, Table, delete, text, update
from sqlalchemy.orm import Session, sessionmaker

from invoice_sorting.control.models import Account, ControlAuthSession, Membership
from invoice_sorting.control.repository import account_references, find_membership
from invoice_sorting.migration.accounts_file import (
    ACCOUNT_ID_MAX,
    AccountRecord,
    AccountsFile,
    is_valid_username,
)
from invoice_sorting.migration.accounts_plan import (
    AccountPlan,
    IdMove,
    build_plan,
    has_usable_admin,
    load_local_accounts,
    plan_section,
)
from invoice_sorting.migration.errors import ImportRejectedError
from invoice_sorting.migration.report import SectionReport
from invoice_sorting.users.deletion import remove_from_control

logger = logging.getLogger(__name__)

ACCOUNT_TABLE = Account.__tablename__
MSG_NO_ADMIN = (
    "恢复后将没有可用的管理员账号（需启用中且已设置密码），已中止导入；"
    "请换一个包含可用管理员的备份，或先在本机保留一个可用的管理员账号"
)


@dataclass(frozen=True)
class AccountsRestoreResult:
    """执行结果：报告分区与会话被失效的账号数（不含任何哈希）。"""

    section: SectionReport
    count: int
    invalidated_ids: tuple[int, ...]
    # 被删除的本地账号 (id, 用户名)：业务库打开后据此把镜像行标记为已删除
    deleted: tuple[tuple[int, str], ...] = ()


def preflight(
    control_factory: sessionmaker[Session],
    tenant_id: int | None,
    accounts: AccountsFile,
    actor_id: int | None = None,
) -> AccountPlan:
    """只读规划并检查管理员；不满足时抛出 ImportRejectedError（尚未写入任何数据）。"""
    with control_factory() as control:
        local = load_local_accounts(control, tenant_id)
    plan = build_plan(accounts.accounts, local, actor_id=actor_id)
    if not plan.has_usable_admin:
        raise ImportRejectedError(MSG_NO_ADMIN)
    return plan


def business_usernames(db_path: Path) -> dict[int, str]:
    """新业务库里的用户 {id: 用户名}；库还没有被运行时打开，直接只读查询。

    业务库同样来自外部包：id 越界、用户名不是合规字符串的行一律忽略，
    与 accounts.json 的校验口径一致，避免异常值参与新 id 的分配。
    """
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        rows = conn.execute("select id, username from app_user").fetchall()
    return {row[0]: row[1] for row in rows if _is_valid_business_row(row[0], row[1])}


def _is_valid_business_row(user_id: object, username: object) -> bool:
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        return False
    return 1 <= user_id <= ACCOUNT_ID_MAX and is_valid_username(username)


def restore_accounts(
    control_factory: sessionmaker[Session],
    tenant_id: int,
    accounts: AccountsFile,
    business_users: Mapping[int, str],
    actor_id: int | None = None,
) -> AccountsRestoreResult:
    """在一个事务里写回账号；失败（含管理员复核不通过）时回滚控制库并抛出。"""
    with control_factory() as control:
        try:
            local = load_local_accounts(control, tenant_id)
            plan = build_plan(accounts.accounts, local, business_users, actor_id)
            _delete(control, tenant_id, plan, actor_id)
            _apply(control, tenant_id, plan)
            control.commit()
        except BaseException:
            control.rollback()
            raise
    logger.info(
        "已恢复登录账号 %s 个（删除 %s 个，id 调整 %s 处），%s 个账号的会话已失效",
        len(plan.changes),
        len(plan.deleted),
        len(plan.moves),
        len(plan.invalidated_ids),
    )
    return AccountsRestoreResult(
        section=plan_section(plan),
        count=len(plan.changes),
        invalidated_ids=plan.invalidated_ids,
        deleted=tuple((account.id, account.username) for account in plan.deleted),
    )


def _delete(control: Session, tenant_id: int, plan: AccountPlan, actor_id: int | None) -> None:
    """先删掉备份里没有的本地账号，腾出它们的 id 与用户名；业务库镜像稍后再标记。"""
    for account in plan.deleted:
        remove_from_control(control, account.id, actor_id=actor_id, tenant_id=tenant_id)


def _apply(control: Session, tenant_id: int, plan: AccountPlan) -> None:
    _rekey(control, plan.moves)
    control.expunge_all()  # 身份映射里的旧对象按旧 id 登记，改 id 后一律丢弃重新读取
    for change in plan.changes:
        _upsert(control, tenant_id, change.record)
    control.flush()
    invalidate_sessions(control, plan.invalidated_ids)
    if not has_usable_admin(control, tenant_id):
        raise ImportRejectedError(MSG_NO_ADMIN)


def invalidate_sessions(control: Session, account_ids: Iterable[int]) -> None:
    ids = list(account_ids)
    if ids:
        control.execute(delete(ControlAuthSession).where(ControlAuthSession.account_id.in_(ids)))


def _upsert(control: Session, tenant_id: int, record: AccountRecord) -> None:
    """按备份值写入账号（平台管理员标记与创建时间保持本地原样）与本账套成员关系。"""
    account = control.get(Account, record.id)
    if account is None:
        account = Account(id=record.id, username=record.username, is_platform_admin=False)
        account.source = record.source
        control.add(account)
    account.display_name = record.display_name
    account.password_hash = record.password_hash
    account.is_active = record.is_active
    control.flush()
    membership = find_membership(control, record.id, tenant_id)
    if membership is None:
        membership = Membership(account_id=record.id, tenant_id=tenant_id)
        control.add(membership)
    membership.role = record.role
    membership.is_active = record.is_active


def _rekey(control: Session, moves: tuple[IdMove, ...]) -> None:
    """两步改 id：old → -old → new；外键列同步改写，外键检查推迟到提交。"""
    if not moves:
        return
    # pysqlite 在第一条写语句前才开启事务；先开事务，defer_foreign_keys 才会作用于本事务
    control.execute(text(f"UPDATE {ACCOUNT_TABLE} SET id = id WHERE 0"))
    control.execute(text("PRAGMA defer_foreign_keys = ON"))
    references = account_references()
    for move in moves:
        _move(control, references, move.old, -move.old)
    for move in moves:
        _move(control, references, -move.old, move.new)


def _move(control: Session, references: list[tuple[Table, Column]], old: int, new: int) -> None:
    table = Account.__table__
    control.execute(update(table).where(table.c.id == old).values(id=new))
    for ref_table, column in references:
        control.execute(update(ref_table).where(column == old).values({column.name: new}))
