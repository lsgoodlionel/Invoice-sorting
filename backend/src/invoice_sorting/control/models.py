"""控制库数据模型（设计 2.1）。

独立的 DeclarativeBase 与独立的 SQLite 文件（control.db），不与业务库 Base 混用，
因此表名可以与业务库重名（例如 auth_session）。时间统一为 Asia/Shanghai 带时区 datetime。
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Connection,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    event,
    func,
    select,
)
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import DeclarativeBase, Mapped, Mapper, mapped_column

from invoice_sorting.db.models import now

TENANT_STATUS_ACTIVE = "active"
TENANT_STATUS_SUSPENDED = "suspended"
TENANT_STATUS_CLOSED = "closed"

ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"

LICENSE_STATUS_ACTIVE = "active"

# 账号来源：空串为正常开通；import 为合并导入账本时创建的停用占位账号（账本搬迁设计 4.3）
ACCOUNT_SOURCE_IMPORT = "import"

ACCOUNT_FK = "account.id"
TENANT_FK = "tenant.id"


class ControlBase(DeclarativeBase):
    """控制库的声明基类；与业务库 Base 相互独立。"""


class Plan(ControlBase):
    """套餐：额度为 0 表示不限制（额度校验在批次三实现）。"""

    __tablename__ = "plan"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(50), default="")
    max_users: Mapped[int] = mapped_column(Integer, default=0)
    max_storage_mb: Mapped[int] = mapped_column(Integer, default=0)
    max_expenses_per_month: Mapped[int] = mapped_column(Integer, default=0)
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Tenant(ControlBase):
    """租户（账套）。slug 全局唯一且小写，决定子域名与数据目录。"""

    __tablename__ = "tenant"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(100), default="")
    status: Mapped[str] = mapped_column(String(20), default=TENANT_STATUS_ACTIVE)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plan.id"), nullable=True)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    # 数据目录名；留空表示按 slug 推导（单租户 default 仍在 data_dir 根目录）
    data_dirname: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Account(ControlBase):
    """控制面账号：全局唯一用户名（可为邮箱），登录统一走控制面。"""

    __tablename__ = "account"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(120), unique=True)
    display_name: Mapped[str] = mapped_column(String(32), default="")
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="")


class IdSequence(ControlBase):
    """已用过的最大 id（只增不减，效果同 SQLite 的 AUTOINCREMENT）。

    账号删除后业务库仍保留同 id 的镜像行（历史记录显示原姓名）；若新账号复用这个 id，
    它就会“继承”那些历史记录。因此账号 id 一律按本表分配，删除时也把 id 记进来。
    """

    __tablename__ = "id_sequence"

    name: Mapped[str] = mapped_column(String(30), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0)


ACCOUNT_ID_SEQUENCE = Account.__tablename__


def remember_account_id(connection: Connection, account_id: int) -> None:
    """把 account_id 记为已用过（只增不减）。"""
    stmt = sqlite_insert(IdSequence).values(name=ACCOUNT_ID_SEQUENCE, value=account_id)
    connection.execute(
        stmt.on_conflict_do_update(
            index_elements=[IdSequence.name],
            set_={"value": func.max(IdSequence.value, stmt.excluded.value)},
        )
    )


def next_account_id(connection: Connection) -> int:
    """比现存账号与曾经用过的 id 都大的新 id，并立即记下（同一次 flush 内连续分配也不重复）。"""
    used = connection.scalar(select(func.max(Account.id))) or 0
    recorded = connection.scalar(
        select(IdSequence.value).where(IdSequence.name == ACCOUNT_ID_SEQUENCE)
    )
    new_id = max(used, recorded or 0) + 1
    remember_account_id(connection, new_id)
    return new_id


@event.listens_for(Account, "before_insert")
def _assign_account_id(_mapper: Mapper, connection: Connection, target: Account) -> None:
    """未显式指定 id 的新账号（显式指定用于迁移与恢复时保持原 id）。"""
    if target.id is None:
        target.id = next_account_id(connection)


class Membership(ControlBase):
    """账号在某租户内的身份；同一账号在同一租户最多一条。"""

    __tablename__ = "membership"
    __table_args__ = (UniqueConstraint("account_id", "tenant_id", name="uq_membership_account"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey(ACCOUNT_FK), index=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey(TENANT_FK), index=True)
    role: Mapped[str] = mapped_column(String(20), default=ROLE_MEMBER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ControlAuthSession(ControlBase):
    """登录会话（控制面）。只保存令牌的 SHA-256；tenant_id 为会话当前所选租户。"""

    __tablename__ = "auth_session"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey(ACCOUNT_FK), index=True)
    tenant_id: Mapped[int | None] = mapped_column(ForeignKey(TENANT_FK), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    user_agent: Mapped[str] = mapped_column(String(200), default="")


class Invite(ControlBase):
    """租户成员邀请码（批次四使用）。"""

    __tablename__ = "invite"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey(TENANT_FK), index=True)
    role: Mapped[str] = mapped_column(String(20), default=ROLE_MEMBER)
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    used_by: Mapped[int | None] = mapped_column(ForeignKey(ACCOUNT_FK), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class UsageSnapshot(ControlBase):
    """租户用量日快照（批次三写入）。"""

    __tablename__ = "usage_snapshot"
    __table_args__ = (UniqueConstraint("tenant_id", "day", name="uq_usage_tenant_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey(TENANT_FK), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    users: Mapped[int] = mapped_column(Integer, default=0)
    storage_bytes: Mapped[int] = mapped_column(Integer, default=0)
    expenses_created: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LicenseRecord(ControlBase):
    """控制面签发的私有化授权。valid_until 为空表示永久授权。

    平台管理员的增删改查在批次四补齐；本表已包含签发所需的全部字段：
    客户名、用户数上限、有效期、状态、可选功能开关，以及首次校验时绑定的实例。
    """

    __tablename__ = "license_record"

    id: Mapped[int] = mapped_column(primary_key=True)
    license_key: Mapped[str] = mapped_column(String(128), unique=True)
    customer_name: Mapped[str] = mapped_column(String(100), default="")
    max_users: Mapped[int] = mapped_column(Integer, default=0)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=LICENSE_STATUS_ACTIVE)
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    # 首次校验成功后绑定的实例；换机需由平台管理员清空
    bound_instance_id: Mapped[str] = mapped_column(String(64), default="")
    note: Mapped[str] = mapped_column(String(200), default="")
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class LicenseToken(ControlBase):
    """私有化实例本地缓存的授权令牌与最近校验结果（单行，id 固定为 1）。

    与 `license_record` 分开：那张表是**签发方**的账本，这张表是**被授权实例**的本地状态。
    出于安全考虑只保存密钥的 SHA-256，不保存密钥本身与原始令牌。
    """

    __tablename__ = "license_token"

    id: Mapped[int] = mapped_column(primary_key=True)
    instance_id: Mapped[str] = mapped_column(String(64), default="")
    license_key_hash: Mapped[str] = mapped_column(String(64), default="")
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_users: Mapped[int] = mapped_column(Integer, default=0)
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(String(300), default="")
    server_reachable: Mapped[bool] = mapped_column(Boolean, default=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
