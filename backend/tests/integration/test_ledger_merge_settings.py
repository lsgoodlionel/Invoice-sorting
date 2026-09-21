"""合并导入 ·「同时导入系统设置」：为 True 以包为准，为 False 保留本地；版本标记永不导入。

测试数据全部虚构：单位名称、税号、商城名称均为编造。
"""

from pathlib import Path

import pytest
from sqlalchemy import select

from invoice_sorting import main
from invoice_sorting.db.models import AppSetting, Category, ChecklistRule, MerchantMemory
from invoice_sorting.db.seed import KEYWORDS_VERSION_KEY
from invoice_sorting.migration.merge import merge_import, preview_import, preview_merge
from invoice_sorting.settings.service import get_app_settings, update_app_settings
from tests.merge_helpers import CUSTOM_CATEGORY, export_source, open_target, seed_rich_ledger

TARGET = "merge-settings"
SOURCE_SETTINGS = {
    "buyer_name": "虚构理工大学",
    "buyer_tax_id": "99ABCDEFGHIJKLMN0X",
    "local_region": "北京",
    "detail_platforms": ["虚构商城"],
    "overdue_days": 45,
}
OFFICE = "办公用品"


def _seed_source(db) -> None:
    update_app_settings(db, **SOURCE_SETTINGS)
    db.merge(AppSetting(key=KEYWORDS_VERSION_KEY, value="2"))  # 低于本机，允许导入
    office = db.scalars(select(Category).where(Category.name == OFFICE)).one()
    office.color, office.keywords, office.route_hint = "pink", ["虚构办公词"], "虚构办理路径"
    db.commit()


@pytest.fixture
def source(app, settings, session, tmp_path):
    seed_rich_ledger(session, settings, tmp_path / "来源")
    _seed_source(session)
    return app


@pytest.fixture
def archive(source, tmp_path) -> Path:
    return export_source(source, tmp_path / "包.zip")


@pytest.fixture
def target(source):
    """目标账本：本地设置不同；同名分类、同位规则与商家记忆都与包内冲突。"""
    context = open_target(source, TARGET)
    with context.session_factory() as db:
        update_app_settings(db, buyer_name="本地虚构单位", overdue_days=60)
        custom = Category(name=CUSTOM_CATEGORY, color="gray", keywords=["本地关键词"])
        other = db.scalars(select(Category).where(Category.name == OFFICE)).one()
        db.add(custom)
        db.flush()
        db.add(ChecklistRule(category_id=custom.id, attachment_kind="contract", hint="本地提示"))
        db.add(
            ChecklistRule(
                category_id=custom.id,
                attachment_kind="contract",
                condition={"amount_gte": 100},
                hint="本地第二条",
            )
        )
        db.add(ChecklistRule(category_id=custom.id, attachment_kind="order", hint="本地独有"))
        db.add(MerchantMemory(seller_name="虚构文具行", category_id=other.id))
        db.commit()
    return context


def _merge(app, archive: Path, include_settings: bool):
    factory = app.state.control_session_factory
    return merge_import(app.state.tenants, factory, archive, TARGET, include_settings)


def _state(context) -> dict:
    with context.session_factory() as db:
        custom = db.scalars(select(Category).where(Category.name == CUSTOM_CATEGORY)).one()
        office = db.scalars(select(Category).where(Category.name == OFFICE)).one()
        rules = db.scalars(select(ChecklistRule).where(ChecklistRule.category_id == custom.id))
        memory = db.get(MerchantMemory, "虚构文具行")
        return {
            "settings": get_app_settings(db),
            "version": db.get(AppSetting, KEYWORDS_VERSION_KEY).value,
            "custom": (custom.color, custom.keywords),
            "office": (office.color, office.keywords, office.route_hint),
            "rules": sorted((rule.attachment_kind, rule.hint) for rule in rules),
            "memory_is_custom": memory.category_id == custom.id,
        }


def test_include_settings_takes_package_values(source, archive, target):
    report = _merge(source, archive, include_settings=True)

    state = _state(target)
    assert state["settings"] == SOURCE_SETTINGS
    assert state["office"] == ("pink", ["虚构办公词"], "虚构办理路径")
    assert state["custom"] == ("pink", ["虚构关键词"])
    assert state["rules"] == [("contract", "虚构提示"), ("order", "本地独有")]
    assert state["memory_is_custom"] is True
    assert report.include_settings is True
    assert report.section("settings").updated == len(SOURCE_SETTINGS)
    assert report.section("rules").updated == 1 and report.section("memories").updated == 1


def test_version_markers_are_never_imported(source, archive, target):
    before = _state(target)["version"]

    _merge(source, archive, include_settings=True)

    assert before != "2" and _state(target)["version"] == before


def test_without_settings_local_values_are_kept(source, archive, target):
    before = _state(target)

    report = _merge(source, archive, include_settings=False)

    after = _state(target)
    assert after == before
    settings_section = report.section("settings")
    assert settings_section.updated == 0 and settings_section.skipped == len(SOURCE_SETTINGS)
    assert all("未勾选" in item.reason for item in settings_section.items)
    assert report.section("rules").conflicts == 1 and report.section("memories").conflicts == 1


def test_preview_lists_setting_changes_without_writing(source, archive, target):
    before = _state(target)

    report = preview_merge(
        source.state.tenants, source.state.control_session_factory, archive, TARGET
    ).to_dict()

    assert _state(target) == before
    section = next(item for item in report["items"] if item["key"] == "settings")
    reasons = {row["label"]: row["reason"] for row in section["details"]}
    assert section["label"] == "系统设置" and section["updated"] == len(SOURCE_SETTINGS)
    assert reasons["报销抬头（买方名称）"] == "本地虚构单位 → 虚构理工大学"
    assert reasons["本地地区"] == "上海 → 北京"
    assert reasons["超期提醒天数"] == "60 → 45"
    assert reasons["已带明细平台"].endswith("→ 虚构商城")
    assert all(row["action"] == "updated" for row in section["details"])
    assert not any("version" in row["label"] for row in section["details"])
    assert report["include_settings"] is True and report["total_updated"] > 0


def test_keys_absent_from_package_do_not_clear_local(app, settings, session, tmp_path):
    seed_rich_ledger(session, settings, tmp_path / "来源")
    update_app_settings(session, buyer_name="虚构只设了抬头")
    session.commit()
    archive = export_source(app, tmp_path / "包.zip")
    context = open_target(app, TARGET)
    with context.session_factory() as db:
        update_app_settings(db, overdue_days=60, local_region="广州")
        db.commit()

    _merge(app, archive, include_settings=True)

    values = _state(context)["settings"]
    assert values["buyer_name"] == "虚构只设了抬头"
    assert values["overdue_days"] == 60 and values["local_region"] == "广州"


def test_invalid_package_value_is_reported_and_local_kept(app, settings, session, tmp_path):
    seed_rich_ledger(session, settings, tmp_path / "来源")
    session.merge(AppSetting(key="overdue_days", value="很多天"))
    session.merge(AppSetting(key="local_region", value="虚" * 30))
    session.commit()
    archive = export_source(app, tmp_path / "包.zip")
    context = open_target(app, TARGET)
    with context.session_factory() as db:
        update_app_settings(db, overdue_days=60)
        db.commit()

    report = _merge(app, archive, include_settings=True)

    values = _state(context)["settings"]
    assert values["overdue_days"] == 60 and values["local_region"] == "上海"
    assert report.section("settings").failed == 2


def test_replace_preview_explains_settings_follow_package(source, archive, target):
    factory = source.state.control_session_factory
    report = preview_import(source.state.tenants, factory, archive, TARGET, "replace")

    assert report["include_settings"] is True
    assert any("系统设置" in warning for warning in report["warnings"])


def test_cli_no_settings_keeps_local(source, archive, target, settings, monkeypatch, capsys):
    monkeypatch.setenv("INVOICE_SORTING_DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("INVOICE_SORTING_WATCH_INBOX", "false")
    source.state.tenants.evict(TARGET)

    main.run(["import-tenant", "--in", str(archive), "--slug", TARGET, "--no-settings"])

    assert "系统设置：新增 0、更新 0" in capsys.readouterr().out
    assert _state(target)["settings"]["buyer_name"] == "本地虚构单位"


def test_cli_defaults_to_including_settings(source, archive, target, settings, monkeypatch):
    monkeypatch.setenv("INVOICE_SORTING_DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("INVOICE_SORTING_WATCH_INBOX", "false")

    main.run(["import-tenant", "--in", str(archive), "--slug", TARGET])

    assert _state(target)["settings"]["buyer_name"] == SOURCE_SETTINGS["buyer_name"]
