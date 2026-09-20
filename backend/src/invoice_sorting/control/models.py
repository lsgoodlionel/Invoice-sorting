"""控制库数据模型（设计 2.1）。

独立的 DeclarativeBase 与独立的 SQLite 文件（control.db），不与业务库 Base 混用，
因此表名可以与业务库重名（例如 auth_session）。时间统一为 Asia/Shanghai 带时区 datetime。
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from invoice_sorting.db.models import now

TENANT_STATUS_ACTIVE = "active"
TENANT_STATUS_SUSPENDED = "suspended"
TENANT_STATUS_CLOSED = "closed"

ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"

LICENSE_STATUS_ACTIVE = "active"

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
    """控制面签发的私有化授权（批次五使用）。"""

    __tablename__ = "license_record"

    id: Mapped[int] = mapped_column(primary_key=True)
    license_key: Mapped[str] = mapped_column(String(128), unique=True)
    customer_name: Mapped[str] = mapped_column(String(100), default="")
    max_users: Mapped[int] = mapped_column(Integer, default=0)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=LICENSE_STATUS_ACTIVE)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
