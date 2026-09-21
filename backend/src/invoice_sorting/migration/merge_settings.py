"""合并导入 · 系统设置（业务库 app_setting）：勾选「同时导入系统设置」时以导入包为准。

只认**白名单**里明确属于“用户设置”的键（USER_SETTING_LABELS）；内部版本标记
（keywords_version / rules_version / classification_memory_version 等）、旧版密码哈希以及
将来任何与本机路径、部署相关的键都不在白名单里，永远不会被导入。

- 只导入包里**确实保存过**的键：包里没设过的项（沿用程序默认值）不去清空本地已有的设置；
- 包内取值先按设置页同一套规则校验，不合法的列为失败、保留本地；
- 未勾选时照样列出差异（动作为“跳过”），方便用户决定要不要勾选。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.db.models import AppSetting
from invoice_sorting.migration.report import (
    ACTION_FAILED,
    ACTION_SKIPPED,
    ACTION_UPDATED,
    SectionBuilder,
    SectionReport,
)
from invoice_sorting.settings.schemas import AppSettingsUpdate
from invoice_sorting.settings.service import REGION_KEYS, get_app_settings, update_app_settings

# 白名单：键 → 报告里显示的中文名。新增用户设置项时须在这里显式登记才会随包导入。
USER_SETTING_LABELS: Mapping[str, str] = MappingProxyType(
    {
        "buyer_name": "报销抬头（买方名称）",
        "buyer_tax_id": "买方税号",
        "local_region": "本地地区",
        "detail_platforms": "已带明细平台",
        "overdue_days": "超期提醒天数",
    }
)
EMPTY_TEXT = "（空）"
LIST_SEPARATOR = "、"
REASON_SKIPPED = "未勾选“同时导入系统设置”，保留本地：{change}"
REASON_INVALID = "包内取值不合法，保留本地"


@dataclass(frozen=True)
class SettingsPlan:
    """将要写入本地的设置（已校验，值为设置页同一形状）。"""

    changes: Mapping[str, Any]

    @property
    def changes_region(self) -> bool:
        return any(key in REGION_KEYS for key in self.changes)


def _display(value: Any) -> str:
    if isinstance(value, list | tuple):
        return LIST_SEPARATOR.join(str(item) for item in value) or EMPTY_TEXT
    text = str(value)
    return text if text.strip() else EMPTY_TEXT


def _stored_keys(pkg: Session) -> frozenset[str]:
    keys = pkg.scalars(select(AppSetting.key).where(AppSetting.key.in_(USER_SETTING_LABELS)))
    return frozenset(keys)


def _is_valid(pkg: Session, key: str, value: Any) -> bool:
    """按设置页的请求校验规则检查包内取值（数值项还要求原始文本本身就是数字）。"""
    if key == "overdue_days":
        raw = pkg.get(AppSetting, key)
        if raw is None or not raw.value.isdigit():
            return False
    try:
        AppSettingsUpdate(**{key: value})
    except ValidationError:
        return False
    return True


def plan_settings(
    pkg: Session, db: Session, include_settings: bool
) -> tuple[SettingsPlan, SectionReport]:
    stored = _stored_keys(pkg)
    incoming = get_app_settings(pkg)
    local = get_app_settings(db)
    changes: dict[str, Any] = {}
    report = SectionBuilder()
    for key, label in USER_SETTING_LABELS.items():
        if key not in stored or incoming[key] == local[key]:
            continue
        if not _is_valid(pkg, key, incoming[key]):
            report.add(ACTION_FAILED, label, REASON_INVALID)
            continue
        change = f"{_display(local[key])} → {_display(incoming[key])}"
        if include_settings:
            changes[key] = incoming[key]
            report.add(ACTION_UPDATED, label, change)
        else:
            report.add(ACTION_SKIPPED, label, REASON_SKIPPED.format(change=change))
    return SettingsPlan(changes=MappingProxyType(changes)), report.build()


def apply_settings(db: Session, plan: SettingsPlan) -> None:
    """写入已规划的设置（复用设置页的规范化逻辑）；由调用方统一提交或回滚。"""
    if plan.changes:
        update_app_settings(db, **dict(plan.changes))
