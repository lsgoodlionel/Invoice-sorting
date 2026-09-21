"""平台注册设置（单行）：审批开关、每月推荐名额、注册码有效天数。"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from invoice_sorting.control.signup_models import SETTINGS_ROW_ID, SignupSettings
from invoice_sorting.db.models import now
from invoice_sorting.signup.codes import new_ip_salt


@dataclass(frozen=True)
class SettingsChange:
    """只包含客户端明确传了的字段；None 表示不修改。"""

    require_approval: bool | None = None
    monthly_referral_quota: int | None = None
    code_valid_days: int | None = None


def load_settings(control: Session) -> SignupSettings:
    """取设置行；不存在时按默认值创建（同时生成本实例的 IP 哈希盐）。调用方负责提交。"""
    row = control.get(SignupSettings, SETTINGS_ROW_ID)
    if row is None:
        row = SignupSettings(id=SETTINGS_ROW_ID, ip_salt=new_ip_salt())
        control.add(row)
        control.flush()
    if not row.ip_salt:
        row.ip_salt = new_ip_salt()
        control.flush()
    return row


def update_settings(control: Session, change: SettingsChange, operator_id: int | None):
    row = load_settings(control)
    if change.require_approval is not None:
        row.require_approval = change.require_approval
    if change.monthly_referral_quota is not None:
        row.monthly_referral_quota = change.monthly_referral_quota
    if change.code_valid_days is not None:
        row.code_valid_days = change.code_valid_days
    row.updated_by = operator_id
    row.updated_at = now()
    control.flush()
    return row
