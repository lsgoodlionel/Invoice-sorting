"""数据模型。金额字段一律为 INTEGER（分），日期为 date，时间为带时区 datetime（Asia/Shanghai）。"""

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from invoice_sorting.auth.context import current_user_id

TZ = ZoneInfo("Asia/Shanghai")


def now() -> datetime:
    return datetime.now(TZ)


class Base(DeclarativeBase):
    pass


USER_FK = "app_user.id"


def actor_column() -> Mapped[int | None]:
    """上传人/操作人外键：默认取当前请求的登录用户（未认证、关闭认证、收件箱为空）。"""
    return mapped_column(ForeignKey(USER_FK), nullable=True, default=current_user_id)


def actor_relationship(column: str) -> Any:
    return relationship(foreign_keys=column, lazy="selectin")


class User(Base):
    """用户。用户名存储为小写且唯一；用户不物理删除，停用后历史记录仍显示姓名。"""

    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    display_name: Mapped[str] = mapped_column(String(32))
    role: Mapped[str] = mapped_column(String(20), default="member")
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 账号已从控制库删除：镜像行保留（历史记录仍显示原姓名），不再参与登录与账号迁移
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Category(Base):
    __tablename__ = "category"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    color: Mapped[str] = mapped_column(String(20), default="gray")
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    route_hint: Mapped[str] = mapped_column(Text, default="")  # 办理路径说明
    sort: Mapped[int] = mapped_column(Integer, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class Project(Base):
    __tablename__ = "project"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), default="")
    name: Mapped[str] = mapped_column(String(100))
    owner: Mapped[str] = mapped_column(String(50), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ChecklistRule(Base):
    """凭证清单模板项。category_id 为空表示通用规则（所有分类继承）。

    condition 为 JSON，支持键（全部满足才触发，空对象表示总是触发）：
      amount_gte: int（分）  amount_lt: int（分）  is_online: bool
      is_nonlocal: bool（外地发票）  detail_platform: bool（销售方属于已带明细平台）
      invoice_exempt: bool（免发票记录，如境外订阅）
    """

    __tablename__ = "checklist_rule"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("category.id"), nullable=True)
    attachment_kind: Mapped[str] = mapped_column(String(30))
    level: Mapped[str] = mapped_column(String(20), default="required")
    condition: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    hint: Mapped[str] = mapped_column(Text, default="")


class Batch(Base):
    __tablename__ = "batch"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("project.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    sent_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    sent_via: Mapped[str] = mapped_column(String(50), default="")
    receiver: Mapped[str] = mapped_column(String(50), default="")
    external_no: Mapped[str] = mapped_column(String(100), default="")
    received_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    received_cents: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    created_by_id: Mapped[int | None] = actor_column()

    project: Mapped[Project | None] = relationship()
    created_by: Mapped[User | None] = actor_relationship("Batch.created_by_id")
    expenses: Mapped[list["Expense"]] = relationship(back_populates="batch")
    exports: Mapped[list["ExportRecord"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class Expense(Base):
    __tablename__ = "expense"

    id: Mapped[int] = mapped_column(primary_key=True)
    spent_on: Mapped[date] = mapped_column(Date)
    amount_cents: Mapped[int] = mapped_column(Integer)
    merchant: Mapped[str] = mapped_column(String(200), default="")
    summary: Mapped[str] = mapped_column(String(200), default="")
    category_id: Mapped[int | None] = mapped_column(ForeignKey("category.id"), nullable=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("project.id"), nullable=True)
    pay_method: Mapped[str] = mapped_column(String(30), default="")
    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="spent")
    status_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batch.id"), nullable=True)
    sent_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    reimbursed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    reimbursed_cents: Mapped[int] = mapped_column(Integer, default=0)
    void_reason: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    folder_path: Mapped[str] = mapped_column(String(500), default="")  # 相对 library_dir
    invoice_exempt: Mapped[bool] = mapped_column(Boolean, default=False)  # 免发票（境外消费等）
    currency: Mapped[str] = mapped_column(String(10), default="CNY")  # 原币种
    original_amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 原币金额
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    created_by_id: Mapped[int | None] = actor_column()

    category: Mapped[Category | None] = relationship()
    project: Mapped[Project | None] = relationship()
    created_by: Mapped[User | None] = actor_relationship("Expense.created_by_id")
    batch: Mapped[Batch | None] = relationship(back_populates="expenses")
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="expense")
    checklist_items: Mapped[list["ChecklistItem"]] = relationship(
        back_populates="expense", cascade="all, delete-orphan"
    )
    status_events: Mapped[list["StatusEvent"]] = relationship(
        back_populates="expense", cascade="all, delete-orphan", order_by="StatusEvent.at"
    )


class Attachment(Base):
    """附件。expense_id 为空表示“待归属”。file_path 为相对 data_dir 的路径。"""

    __tablename__ = "attachment"

    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int | None] = mapped_column(ForeignKey("expense.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(30), default="other")
    file_path: Mapped[str] = mapped_column(String(500))
    original_name: Mapped[str] = mapped_column(String(300))
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    mime: Mapped[str] = mapped_column(String(100), default="")
    size: Mapped[int] = mapped_column(Integer, default=0)
    file_key: Mapped[str] = mapped_column(String(200), default="")  # 文件名键（设计 3.3）
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    uploaded_by_id: Mapped[int | None] = actor_column()

    expense: Mapped[Expense | None] = relationship(back_populates="attachments")
    uploaded_by: Mapped[User | None] = actor_relationship("Attachment.uploaded_by_id")
    invoice_data: Mapped["InvoiceData | None"] = relationship(
        back_populates="attachment", cascade="all, delete-orphan", uselist=False
    )
    evidence_data: Mapped["EvidenceData | None"] = relationship(
        back_populates="attachment", cascade="all, delete-orphan", uselist=False
    )


class InvoiceData(Base):
    __tablename__ = "invoice_data"

    attachment_id: Mapped[int] = mapped_column(ForeignKey("attachment.id"), primary_key=True)
    invoice_no: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    issued_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tax_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seller_name: Mapped[str] = mapped_column(String(200), default="")
    seller_tax_id: Mapped[str] = mapped_column(String(50), default="")
    buyer_name: Mapped[str] = mapped_column(String(200), default="")
    buyer_tax_id: Mapped[str] = mapped_column(String(50), default="")
    item_summary: Mapped[str] = mapped_column(String(300), default="")
    invoice_type: Mapped[str] = mapped_column(String(50), default="")
    tax_category: Mapped[str] = mapped_column(String(50), default="")
    region_name: Mapped[str] = mapped_column(String(20), default="")  # 开票地区，如“北京”
    order_no: Mapped[str] = mapped_column(String(50), default="")  # 电商订单号
    parser: Mapped[str] = mapped_column(String(50), default="")
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_text: Mapped[str] = mapped_column(Text, default="")

    # 结构化补充信息（火车/飞机票：date、from、to、vehicle、number、passenger），旧库可能为 NULL
    details: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True, default=dict)

    attachment: Mapped[Attachment] = relationship(back_populates="invoice_data")


class EvidenceData(Base):
    """非发票凭证（订单、收据、银行交易、行程单等）的识别结果，与附件 1:1。"""

    __tablename__ = "evidence_data"

    attachment_id: Mapped[int] = mapped_column(ForeignKey("attachment.id"), primary_key=True)
    doc_type: Mapped[str] = mapped_column(String(20), default="unknown")
    recognizer: Mapped[str] = mapped_column(String(50), default="")
    amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 按 currency
    currency: Mapped[str] = mapped_column(String(10), default="CNY")
    cny_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 人民币金额
    occurred_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    merchant: Mapped[str] = mapped_column(String(200), default="")
    item_name: Mapped[str] = mapped_column(String(300), default="")
    order_no: Mapped[str] = mapped_column(String(100), default="")
    card_last4: Mapped[str] = mapped_column(String(4), default="")
    is_foreign: Mapped[bool] = mapped_column(Boolean, default=False)
    file_key: Mapped[str] = mapped_column(String(200), default="")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    # 结构化补充信息（酒店订单：城市、入住离店日期；交通凭证：日期、起止站），旧库可能为 NULL
    details: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True, default=dict)

    attachment: Mapped[Attachment] = relationship(back_populates="evidence_data")


class ChecklistItem(Base):
    __tablename__ = "checklist_item"

    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int] = mapped_column(ForeignKey("expense.id"))
    attachment_kind: Mapped[str] = mapped_column(String(30))
    level: Mapped[str] = mapped_column(String(20), default="required")
    state: Mapped[str] = mapped_column(String(20), default="missing")
    reason: Mapped[str] = mapped_column(Text, default="")
    hint: Mapped[str] = mapped_column(Text, default="")

    expense: Mapped[Expense] = relationship(back_populates="checklist_items")


class StatusEvent(Base):
    __tablename__ = "status_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    expense_id: Mapped[int] = mapped_column(ForeignKey("expense.id"))
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    actor_id: Mapped[int | None] = actor_column()

    expense: Mapped[Expense] = relationship(back_populates="status_events")
    actor: Mapped[User | None] = actor_relationship("StatusEvent.actor_id")


class ExportRecord(Base):
    __tablename__ = "export_record"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batch.id"))
    layout: Mapped[str] = mapped_column(String(20))
    file_path: Mapped[str] = mapped_column(String(500))  # 相对 data_dir
    sha256: Mapped[str] = mapped_column(String(64))
    item_count: Mapped[int] = mapped_column(Integer)
    total_cents: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    created_by_id: Mapped[int | None] = actor_column()

    batch: Mapped[Batch] = relationship(back_populates="exports")
    created_by: Mapped[User | None] = actor_relationship("ExportRecord.created_by_id")


class MerchantMemory(Base):
    """销售方 → 上次使用的分类，用于分类建议。"""

    __tablename__ = "merchant_memory"

    seller_name: Mapped[str] = mapped_column(String(200), primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ItemMemory(Base):
    """发票商品名称 → 用户确认的分类，优先级高于商家记忆（同一商家可能卖不同类商品）。"""

    __tablename__ = "item_memory"

    item_name: Mapped[str] = mapped_column(String(200), primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class AppSetting(Base):
    """键值配置，如 buyer_name / buyer_tax_id / overdue_days。"""

    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class AuthSession(Base):
    """登录会话。只保存令牌的 SHA-256，明文令牌仅存在于客户端 Cookie。"""

    __tablename__ = "auth_session"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    # 旧库补列时无法追加 NOT NULL，启动迁移会删除 user_id 为空的旧会话
    user_id: Mapped[int] = mapped_column(ForeignKey(USER_FK), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    user_agent: Mapped[str] = mapped_column(String(200), default="")
