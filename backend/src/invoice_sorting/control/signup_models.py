"""注册申请与推荐的控制库表（《注册申请与推荐_设计》）。

与 control/models.py 共用 ControlBase，建表与补列都走同一套轻量迁移（只追加）。

凭证的存法按用途权衡：
- **注册码**：凭它能开通账套并登录，等同一次性密码 → 只存 SHA-256，原文只出现在
  邮件与批准/重新发送的那一次响应里；「重新发送」会换发新码，旧码随即失效。
- **推荐码**：本人需要随时查看并复制推荐链接，且它本身只能“进入申请表”、不能开户
  （需审批模式下仍要平台批准，直接注册模式下注册码也只发到申请邮箱）→ 存明文，可重置、可停用。
- **来源 IP**：只存带实例盐的 HMAC-SHA256，用于统计与排查，不能反推出原始地址。
"""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from invoice_sorting.control.models import ACCOUNT_FK, TENANT_FK, ControlBase
from invoice_sorting.db.models import now

APPLICATION_PENDING = "pending"
APPLICATION_APPROVED = "approved"
APPLICATION_REJECTED = "rejected"
APPLICATION_REGISTERED = "registered"
APPLICATION_STATUSES = (
    APPLICATION_PENDING,
    APPLICATION_APPROVED,
    APPLICATION_REJECTED,
    APPLICATION_REGISTERED,
)

# 邮件发送状态：空串为尚未发信；skipped 表示未配置 SMTP，由管理员自行转告
MAIL_NONE = ""
MAIL_SENT = "sent"
MAIL_FAILED = "failed"
MAIL_SKIPPED = "skipped"

SETTINGS_ROW_ID = 1
DEFAULT_REQUIRE_APPROVAL = True
DEFAULT_MONTHLY_REFERRAL_QUOTA = 5
DEFAULT_CODE_VALID_DAYS = 7


class SignupApplication(ControlBase):
    """访客提交的注册申请；批准后发放注册码，注册完成后记录开通的账号与账套。"""

    __tablename__ = "signup_application"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32), default="")
    email: Mapped[str] = mapped_column(String(254), default="", index=True)
    identity: Mapped[str] = mapped_column(String(100), default="")
    needs: Mapped[str] = mapped_column(String(1000), default="")
    ledger_name: Mapped[str] = mapped_column(String(100), default="")
    referrer_account_id: Mapped[int | None] = mapped_column(
        ForeignKey(ACCOUNT_FK), nullable=True, index=True
    )
    ip_hash: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(20), default=APPLICATION_PENDING, index=True)
    # 直接注册模式下由系统自动批准（推荐名额内），此时没有审批人
    is_auto_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewer_account_id: Mapped[int | None] = mapped_column(ForeignKey(ACCOUNT_FK), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reject_reason: Mapped[str] = mapped_column(String(200), default="")
    # 批准时确定的账套开通参数（注册完成时才真正开通）
    approved_slug: Mapped[str] = mapped_column(String(50), default="")
    approved_name: Mapped[str] = mapped_column(String(100), default="")
    approved_plan_code: Mapped[str] = mapped_column(String(30), default="")
    approved_expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mail_status: Mapped[str] = mapped_column(String(20), default=MAIL_NONE)
    mail_error: Mapped[str] = mapped_column(String(200), default="")
    mail_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registered_account_id: Mapped[int | None] = mapped_column(ForeignKey(ACCOUNT_FK), nullable=True)
    registered_tenant_id: Mapped[int | None] = mapped_column(ForeignKey(TENANT_FK), nullable=True)
    registered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 否决满 180 天后清除个人资料，只保留状态与时间用于统计
    is_purged: Mapped[bool] = mapped_column(Boolean, default=False)
    purged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class ReferralCode(ControlBase):
    """每个账号一个推荐码；重置即换新码（旧链接立即失效），平台可停用推荐资格。"""

    __tablename__ = "referral_code"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey(ACCOUNT_FK), unique=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    is_disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SignupSettings(ControlBase):
    """平台注册设置（单行，id 固定为 1）。ip_salt 为本实例的 IP 哈希盐，从不对外返回。"""

    __tablename__ = "signup_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    require_approval: Mapped[bool] = mapped_column(Boolean, default=DEFAULT_REQUIRE_APPROVAL)
    monthly_referral_quota: Mapped[int] = mapped_column(
        Integer, default=DEFAULT_MONTHLY_REFERRAL_QUOTA
    )
    code_valid_days: Mapped[int] = mapped_column(Integer, default=DEFAULT_CODE_VALID_DAYS)
    ip_salt: Mapped[str] = mapped_column(String(64), default="")
    updated_by: Mapped[int | None] = mapped_column(ForeignKey(ACCOUNT_FK), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
