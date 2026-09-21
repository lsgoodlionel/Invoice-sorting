"""应用设置（T20）。"""

import pytest

from invoice_sorting.common.errors import AppError
from invoice_sorting.db.models import AppSetting
from invoice_sorting.settings import service as settings_service
from invoice_sorting.settings.service import (
    get_app_settings,
    update_app_settings,
)

REGION_DEFAULTS = {"local_region": "上海", "detail_platforms": ["京东", "当当", "圆迈"]}


def test_defaults(session):
    assert get_app_settings(session) == {
        "buyer_name": "",
        "buyer_tax_id": "",
        "overdue_days": 30,
        **REGION_DEFAULTS,
    }


def test_update_persists_values(session):
    result = update_app_settings(session, buyer_name="某某大学", overdue_days=45)
    assert result["buyer_name"] == "某某大学"
    assert get_app_settings(session)["overdue_days"] == 45
    update_app_settings(session, buyer_tax_id="12100000")
    assert get_app_settings(session) == {
        "buyer_name": "某某大学",
        "buyer_tax_id": "12100000",
        "overdue_days": 45,
        **REGION_DEFAULTS,
    }


@pytest.mark.parametrize("values", [{"overdue_days": 0}, {"unknown": "x"}])
def test_update_rejects_invalid(session, values):
    with pytest.raises(AppError):
        update_app_settings(session, **values)


def test_region_settings_normalized(session):
    result = update_app_settings(
        session, local_region="  北京 ", detail_platforms=[" 京东", "", "京东", "拼多多 "]
    )
    assert result["local_region"] == "北京"
    assert result["detail_platforms"] == ["京东", "拼多多"]
    policy = settings_service.region_policy(session)
    assert policy.local_region == "北京" and policy.detail_platforms == ("京东", "拼多多")
    assert update_app_settings(session, detail_platforms=[])["detail_platforms"] == []


@pytest.mark.parametrize(
    "values",
    [
        {"detail_platforms": "京东"},
        {"detail_platforms": ["京" * 51]},
        {"detail_platforms": [f"平台{i}" for i in range(51)]},
        {"local_region": "北" * 21},
    ],
)
def test_region_settings_reject_invalid(session, values):
    with pytest.raises(AppError):
        update_app_settings(session, **values)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("京东,当当 , ,圆迈", ["京东", "当当", "圆迈"]),
        ('{"a": 1}', ["京东", "当当", "圆迈"]),
        ('["天猫", "天猫"]', ["天猫"]),
    ],
)
def test_detail_platforms_stored_formats(session, raw, expected):
    session.add(AppSetting(key="detail_platforms", value=raw))
    session.flush()
    assert get_app_settings(session)["detail_platforms"] == expected
