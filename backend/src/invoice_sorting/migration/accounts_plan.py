"""账号恢复规划（账本搬迁设计 3.1）：只读、纯计算，预览与执行共用同一份规划。

规则（仅单账套部署的整套覆盖）：
- 按用户名对位：本地已有 → 更新密码哈希、显示名、角色、启用状态；本地没有 → 新建；
- 本地有、备份没有 → **删除**（执行导入的管理员本人除外，他保留），恢复后的账号与备份时一致；
  删除语义同“用户管理 → 删除用户”（users/deletion.py）：控制库删账号，业务库镜像保留并标记已删除；
- **编号对齐**：覆盖后业务库整体换成备份里的库，其中 `app_user.id` 是备份时的账号 id，
  为保持不变量 `User.id == Account.id`，恢复的账号一律改用备份里的 id；
  被占用的 id 由保留下来的本地账号（执行者本人、不属于本账套的账号）让出：
  它若在新业务库里有同名用户则对齐到那个 id（历史记录随之归位），
  否则换到一个全新的 id（比本地、备份与新业务库里出现过的 id 都大）。
- 恢复后至少要有一个可用的管理员：启用中且设置了密码；
  内置 admin 尚未设密码时可走首次设置，也算可用。
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.control.members import BUILTIN_ADMIN_USERNAME, list_members
from invoice_sorting.control.models import ROLE_ADMIN, Account, Membership
from invoice_sorting.migration.accounts_file import AccountRecord
from invoice_sorting.migration.report import (
    ACTION_ADDED,
    ACTION_DELETED,
    ACTION_SKIPPED,
    ACTION_UPDATED,
    SectionBuilder,
    SectionReport,
)

MIRROR_USERNAME_MAX = 32  # 业务库 app_user.username 的长度（镜像时截断）
ROLE_LABELS = {ROLE_ADMIN: "管理员"}
ROLE_MEMBER_LABEL = "成员"

REASON_CREATE = "新建（可用备份时的密码登录）"
REASON_PASSWORD = "更新密码（恢复为备份时的密码）"
REASON_PROFILE = "更新显示名、角色或启用状态"
REASON_REKEY = "账号编号与备份对齐"
REASON_SAME = "与本地一致"
REASON_KEPT = "备份里没有，但为执行导入的管理员本人，保留"
REASON_DELETE = "备份里没有的本地账号，删除"


@dataclass(frozen=True)
class LocalAccount:
    """本地控制库里的一个账号；role 为它在目标账套的角色（不是该账套成员时为 None）。"""

    id: int
    username: str
    display_name: str
    is_active: bool
    role: str | None = None
    is_member_active: bool = False
    password_hash: str | None = field(default=None, repr=False)

    @property
    def is_usable_admin(self) -> bool:
        is_active = self.is_active and self.is_member_active
        return self.role == ROLE_ADMIN and is_active and _can_sign_in(self)


@dataclass(frozen=True)
class AccountChange:
    """一个备份账号在本地的去向：新建 / 更新 / 不变。"""

    record: AccountRecord
    local: LocalAccount | None

    @property
    def is_created(self) -> bool:
        return self.local is None

    @property
    def is_password_changed(self) -> bool:
        return self.local is not None and self.local.password_hash != self.record.password_hash

    @property
    def is_profile_changed(self) -> bool:
        local, record = self.local, self.record
        if local is None:
            return False
        is_active = local.is_active and local.is_member_active
        return (local.display_name, local.role, is_active) != (
            record.display_name,
            record.role,
            record.is_active,
        )

    @property
    def is_rekeyed(self) -> bool:
        return self.local is not None and self.local.id != self.record.id

    @property
    def is_changed(self) -> bool:
        flags = (self.is_password_changed, self.is_profile_changed, self.is_rekeyed)
        return self.is_created or any(flags)


@dataclass(frozen=True)
class IdMove:
    old: int
    new: int


@dataclass(frozen=True)
class AccountPlan:
    changes: tuple[AccountChange, ...]
    kept: tuple[LocalAccount, ...]
    moves: tuple[IdMove, ...]
    deleted: tuple[LocalAccount, ...] = ()

    @property
    def invalidated_ids(self) -> tuple[int, ...]:
        """需要让登录会话失效的账号（按恢复后的 id）：新建与任何字段被改动的账号。"""
        return tuple(change.record.id for change in self.changes if change.is_changed)

    @property
    def has_usable_admin(self) -> bool:
        restored = any(
            record.role == ROLE_ADMIN and record.is_active and _can_sign_in(record)
            for record in (change.record for change in self.changes)
        )
        return restored or any(account.is_usable_admin for account in self.kept)


def _can_sign_in(account: AccountRecord | LocalAccount) -> bool:
    """有密码，或是尚未设密码的内置 admin（首次设置入口会让管理员设置密码）。"""
    return account.password_hash is not None or account.username == BUILTIN_ADMIN_USERNAME


def has_usable_admin(control: Session, tenant_id: int) -> bool:
    """账套里是否还有可用的管理员（恢复后复核、删除用户都用这一口径）：
    启用中的管理员，有密码或是尚未设密码的内置 admin。"""
    members = list_members(control, tenant_id)
    return any(local_account(m.account, m.membership).is_usable_admin for m in members)


def load_local_accounts(control: Session, tenant_id: int | None) -> tuple[LocalAccount, ...]:
    """控制库全部账号，附带它在目标账套的角色与成员状态（只读）。"""
    memberships: dict[int, Membership] = {}
    if tenant_id is not None:
        rows = control.scalars(select(Membership).where(Membership.tenant_id == tenant_id))
        memberships = {row.account_id: row for row in rows}
    accounts = control.scalars(select(Account).order_by(Account.id))
    return tuple(local_account(account, memberships.get(account.id)) for account in accounts)


def local_account(account: Account, membership: Membership | None) -> LocalAccount:
    """控制库行换算成只读快照（规划与执行后的复核用同一口径）。"""
    return LocalAccount(
        id=account.id,
        username=account.username,
        display_name=account.display_name,
        is_active=bool(account.is_active),
        role=membership.role if membership is not None else None,
        is_member_active=bool(membership.is_active) if membership is not None else False,
        password_hash=account.password_hash,
    )


def build_plan(
    records: Iterable[AccountRecord],
    local_accounts: Iterable[LocalAccount],
    business_users: Mapping[int, str] | None = None,
    actor_id: int | None = None,
) -> AccountPlan:
    """规划账号去向、删除与 id 调整。

    business_users 为新业务库 app_user 的 {id: 用户名}；预览时还没解包，传空。
    actor_id 为执行导入的账号（命令行为 None）：备份里没有他时保留而不删除。
    本账套里备份没有的其他账号一律删除；不属于本账套的账号不删，只在 id 冲突时让位。
    """
    locals_ = tuple(local_accounts)
    by_name = {account.username: account for account in locals_}
    changes = tuple(AccountChange(record, by_name.get(record.username)) for record in records)
    matched = {change.local.id for change in changes if change.local is not None}
    unmatched = tuple(account for account in locals_ if account.id not in matched)
    deleted = tuple(a for a in unmatched if a.role is not None and a.id != actor_id)
    kept = tuple(a for a in unmatched if a not in deleted)
    moves = _moves(changes, kept, locals_, business_users or {})
    return AccountPlan(changes=changes, kept=kept, moves=moves, deleted=deleted)


def _moves(
    changes: tuple[AccountChange, ...],
    kept: tuple[LocalAccount, ...],
    locals_: tuple[LocalAccount, ...],
    business: Mapping[int, str],
) -> tuple[IdMove, ...]:
    moves = [IdMove(c.local.id, c.record.id) for c in changes if c.local and c.is_rekeyed]
    claimed = {change.record.id for change in changes}
    by_name = {name: user_id for user_id, name in business.items()}
    next_id = max([0, *claimed, *(a.id for a in locals_), *business]) + 1
    for account in sorted(kept, key=lambda item: item.id):
        target = _kept_target(account, claimed, business, by_name)
        if target is None:
            target, next_id = next_id, next_id + 1
        claimed.add(target)
        if target != account.id:
            moves.append(IdMove(account.id, target))
    return tuple(moves)


def _kept_target(
    account: LocalAccount,
    claimed: set[int],
    business: Mapping[int, str],
    by_name: Mapping[str, int],
) -> int | None:
    """本地独有账号的新 id：新业务库里的同名用户优先；原 id 未被占用则不动；否则 None（另分配）。"""
    mirror_name = account.username[:MIRROR_USERNAME_MAX]
    same_name = by_name.get(mirror_name)
    if same_name is not None and same_name not in claimed:
        return same_name
    owner = business.get(account.id)
    if account.id in claimed or (owner is not None and owner != mirror_name):
        return None
    return account.id


def plan_section(plan: AccountPlan) -> SectionReport:
    """报告里的 accounts 分区：新建 / 更新（更新密码或资料）/ 不变 / 删除 / 执行者本人保留。"""
    builder = SectionBuilder()
    for change in plan.changes:
        label = _label(change.record.username, change.record.role)
        if change.is_created:
            builder.add(ACTION_ADDED, label, REASON_CREATE)
        elif change.is_changed:
            builder.add(ACTION_UPDATED, label, _update_reason(change))
        else:
            builder.add(ACTION_SKIPPED, label, REASON_SAME)
    for account in plan.deleted:
        builder.add(ACTION_DELETED, _label(account.username, account.role or ""), REASON_DELETE)
    for account in plan.kept:
        if account.role is not None:
            builder.add(ACTION_SKIPPED, _label(account.username, account.role), REASON_KEPT)
    return builder.build()


def _update_reason(change: AccountChange) -> str:
    reasons = [
        *([REASON_PASSWORD] if change.is_password_changed else []),
        *([REASON_PROFILE] if change.is_profile_changed else []),
        *([REASON_REKEY] if change.is_rekeyed else []),
    ]
    return "；".join(reasons)


def _label(username: str, role: str) -> str:
    return f"{username}（{ROLE_LABELS.get(role, ROLE_MEMBER_LABEL)}）"
