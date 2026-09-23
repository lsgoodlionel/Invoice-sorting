"""平台邮件（SMTP）设置：控制库单行表，由平台管理员在网页上填写。

密码只存 Fernet 密文（密钥见 common/secret_box.py，不入库）；任何接口都不返回密码或密文。
同时记录最后修改人与最近一次验证（测试连接 / 测试邮件）的结果，便于排查。
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from invoice_sorting.config import DEFAULT_SMTP_PORT, SMTP_TLS_SSL
from invoice_sorting.control.models import ACCOUNT_FK, ControlBase

MAIL_SETTINGS_ROW_ID = 1


class MailSettings(ControlBase):
    """邮件设置（仅一行，id 固定为 1）。"""

    __tablename__ = "mail_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    host: Mapped[str] = mapped_column(String(253), default="")
    port: Mapped[int] = mapped_column(Integer, default=DEFAULT_SMTP_PORT)
    username: Mapped[str] = mapped_column(String(254), default="")
    password_encrypted: Mapped[str] = mapped_column(Text, default="")
    sender: Mapped[str] = mapped_column(String(320), default="")
    tls: Mapped[str] = mapped_column(String(16), default=SMTP_TLS_SSL)
    public_base_url: Mapped[str] = mapped_column(String(300), default="")
    # 有新申请待审批时提醒谁：英文逗号分隔，最多 5 个；留空表示不发提醒
    notify_emails: Mapped[str] = mapped_column(String(1300), default="")
    updated_by: Mapped[int | None] = mapped_column(ForeignKey(ACCOUNT_FK), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 最近一次验证：kind 为 connection / email；category 为失败分类（成功时为 ok）
    last_check_kind: Mapped[str] = mapped_column(String(16), default="")
    last_check_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    last_check_category: Mapped[str] = mapped_column(String(16), default="")
    last_check_message: Mapped[str] = mapped_column(String(200), default="")
    last_checked_by: Mapped[int | None] = mapped_column(ForeignKey(ACCOUNT_FK), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
