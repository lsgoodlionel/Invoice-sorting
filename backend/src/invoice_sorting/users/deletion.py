"""删除账号（可复用）：从控制库删除账号在本账套的身份，业务库镜像保留并标记为已删除。

供“用户管理 → 删除用户”与“单账套整套覆盖恢复账号”（账本搬迁设计 3.1）共用：

    delete_account(control, business, account_id, *, actor_id, tenant_id) -> DeletedAccount

- 不能删除执行者本人（actor_id），否则 400；
- 控制库：删除该账号在本账套的成员关系与会话；若它在别的账套已没有成员关系（单账套必然如此）
  且不是平台管理员，则连账号行一并删除，其他表里指向它的可空引用（邀请使用人、设置修改人等）置空，
  不可空的附属行（如推荐码）随之删除，该 id 记入 `id_sequence` 不再分配给新账号；
  仍属于别的账套时账号保留，只移出本账套；
- 业务库：同 id 的 `app_user` 镜像行保留，`is_active=False`、`is_deleted=True`、记下 `deleted_at`，
  历史记录的上传人/操作人仍显示原姓名；用户名在有人重新使用时才改名让位（users/mirror.py）。
两边都只 flush 不提交，提交与回滚由调用方统一处理。
"""

from dataclasses import dataclass

from sqlalchemy import Column, Table, delete, func, select, update
from sqlalchemy.orm import Session

from invoice_sorting.common.errors import AppError, NotFoundError
from invoice_sorting.control.models import (
    Account,
    ControlAuthSession,
    Membership,
    remember_account_id,
)
from invoice_sorting.control.repository import account_references
from invoice_sorting.db.models import User, now

MSG_DELETE_SELF = "不能删除自己的账号"
WHAT_ACCOUNT = "账号"
MIRROR_USERNAME_MAX = 32
# 这些表的外键由删除流程显式处理，不走通用的“置空/删除附属行”
HANDLED_TABLES = frozenset({Membership.__tablename__, ControlAuthSession.__tablename__})


@dataclass(frozen=True)
class DeletedAccount:
    account_id: int
    username: str
    is_account_removed: bool  # False：账号仍属于别的账套，只移出了本账套


def delete_account(
    control: Session,
    business: Session | None,
    account_id: int,
    *,
    actor_id: int | None,
    tenant_id: int,
) -> DeletedAccount:
    """删除账号在本账套的身份并标记业务库镜像。

    business 为 None 时只处理控制库，由调用方稍后调用 mark_mirror_deleted。
    """
    deleted = remove_from_control(control, account_id, actor_id=actor_id, tenant_id=tenant_id)
    if business is not None:
        mark_mirror_deleted(business, account_id, deleted.username)
    return deleted


def remove_from_control(
    control: Session, account_id: int, *, actor_id: int | None, tenant_id: int
) -> DeletedAccount:
    if actor_id is not None and account_id == actor_id:
        raise AppError(MSG_DELETE_SELF, status_code=400)
    account = control.get(Account, account_id)
    if account is None:
        raise NotFoundError(WHAT_ACCOUNT)
    username = account.username
    control.execute(
        delete(Membership).where(
            Membership.account_id == account_id, Membership.tenant_id == tenant_id
        )
    )
    others = control.scalar(
        select(func.count()).select_from(Membership).where(Membership.account_id == account_id)
    )
    is_removed = not others and not account.is_platform_admin
    if is_removed:
        _remove_account_row(control, account)
    else:
        control.execute(
            delete(ControlAuthSession).where(
                ControlAuthSession.account_id == account_id,
                ControlAuthSession.tenant_id == tenant_id,
            )
        )
    control.flush()
    return DeletedAccount(account_id, username, is_removed)


def _remove_account_row(control: Session, account: Account) -> None:
    account_id = account.id
    # 记下这个 id：之后的新账号不再复用，否则会“继承”业务库镜像里此人的历史记录
    remember_account_id(control.connection(), account_id)
    control.execute(delete(ControlAuthSession).where(ControlAuthSession.account_id == account_id))
    for table, column in _other_references():
        if column.nullable:
            control.execute(update(table).where(column == account_id).values({column.name: None}))
        else:
            control.execute(delete(table).where(column == account_id))
    control.delete(account)


def _other_references() -> list[tuple[Table, Column]]:
    """引用 account.id 的其他外键列：可空的置空，不可空的附属行随账号删除。"""
    return [(t, c) for t, c in account_references() if t.name not in HANDLED_TABLES]


def mark_mirror_deleted(business: Session, account_id: int, username: str) -> bool:
    """把镜像行标记为已删除；该 id 的行不存在或属于别的用户名（例如刚换进来的业务库）时不动。"""
    user = business.get(User, account_id)
    if user is None or user.username != username[:MIRROR_USERNAME_MAX]:
        return False
    user.is_active = False
    user.is_deleted = True
    user.deleted_at = now()
    business.flush()
    return True
