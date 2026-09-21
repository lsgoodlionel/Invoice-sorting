"""应用设置（键值表）。"""

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.checklist.regions import (
    DEFAULT_DETAIL_PLATFORMS,
    DEFAULT_LOCAL_REGION,
    RegionPolicy,
)
from invoice_sorting.common.errors import AppError
from invoice_sorting.db.models import AppSetting

DEFAULT_OVERDUE_DAYS = 30
MAX_OVERDUE_DAYS = 3650
REGION_MAX = 20
PLATFORM_MAX = 50
MAX_PLATFORMS = 50
TEXT_KEYS = ("buyer_name", "buyer_tax_id")
INT_KEYS = ("overdue_days",)
REGION_KEYS = frozenset({"local_region", "detail_platforms"})


def _parse_platforms(raw: str | None) -> list[str]:
    if raw is None:
        return list(DEFAULT_DETAIL_PLATFORMS)
    try:
        values = json.loads(raw)
    except ValueError:
        values = raw.split(",")
    if not isinstance(values, list):
        return list(DEFAULT_DETAIL_PLATFORMS)
    return clean_platforms(str(value) for value in values)


def clean_platforms(values: Any) -> list[str]:
    """去空白、去空项、去重（保持顺序）。"""
    stripped = (str(value).strip() for value in values)
    return list(dict.fromkeys(value for value in stripped if value))


def get_app_settings(session: Session) -> dict[str, Any]:
    stored = {row.key: row.value for row in session.scalars(select(AppSetting))}
    overdue = stored.get("overdue_days", "")
    return {
        "buyer_name": stored.get("buyer_name", ""),
        "buyer_tax_id": stored.get("buyer_tax_id", ""),
        "overdue_days": int(overdue) if overdue.isdigit() else DEFAULT_OVERDUE_DAYS,
        "local_region": stored.get("local_region", DEFAULT_LOCAL_REGION),
        "detail_platforms": _parse_platforms(stored.get("detail_platforms")),
    }


def _normalize_platforms(value: Any) -> str:
    if not isinstance(value, list | tuple):
        raise AppError("已带明细平台必须是文本列表")
    platforms = clean_platforms(value)
    if len(platforms) > MAX_PLATFORMS:
        raise AppError(f"已带明细平台最多 {MAX_PLATFORMS} 个")
    if any(len(item) > PLATFORM_MAX for item in platforms):
        raise AppError(f"平台关键词不能超过 {PLATFORM_MAX} 个字")
    return json.dumps(platforms, ensure_ascii=False)


def _normalize_region(value: Any) -> str:
    region = str(value or "").strip()
    if len(region) > REGION_MAX:
        raise AppError(f"本地地区不能超过 {REGION_MAX} 个字")
    return region


def _normalize(key: str, value: Any) -> str:
    if key in TEXT_KEYS:
        return str(value or "").strip()
    if key == "local_region":
        return _normalize_region(value)
    if key == "detail_platforms":
        return _normalize_platforms(value)
    if key in INT_KEYS:
        if isinstance(value, bool) or not isinstance(value, int):
            raise AppError("超期提醒天数必须是整数")
        if not 1 <= value <= MAX_OVERDUE_DAYS:
            raise AppError(f"超期提醒天数需在 1–{MAX_OVERDUE_DAYS} 之间")
        return str(value)
    raise AppError(f"未知设置项：{key}")


def update_app_settings(session: Session, **values: Any) -> dict[str, Any]:
    normalized = {key: _normalize(key, value) for key, value in values.items()}
    for key, value in normalized.items():
        row = session.get(AppSetting, key)
        if row is None:
            session.add(AppSetting(key=key, value=value))
        else:
            row.value = value
    session.flush()
    return get_app_settings(session)


def region_policy(session: Session) -> RegionPolicy:
    values = get_app_settings(session)
    return RegionPolicy(values["local_region"], tuple(values["detail_platforms"]))


def buyer_identity(session: Session) -> tuple[str, str]:
    values = get_app_settings(session)
    return values["buyer_name"], values["buyer_tax_id"]
