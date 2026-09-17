"""默认清单规则同步：旧库追加外地订单规则，幂等且不重复、不恢复用户删除的旧规则。"""

from sqlalchemy import delete, func, select

from invoice_sorting.db import seed
from invoice_sorting.db.models import AppSetting, Category, ChecklistRule
from invoice_sorting.db.seed import (
    NONLOCAL_ORDER_RULE,
    RULES_VERSION,
    RULES_VERSION_KEY,
    sync_default_rules,
)

NONLOCAL_CONDITION = {"is_nonlocal": True, "detail_platform": False}


def nonlocal_rules(session) -> list[ChecklistRule]:
    query = select(ChecklistRule).where(
        ChecklistRule.category_id.is_(None), ChecklistRule.attachment_kind == "order"
    )
    return [rule for rule in session.scalars(query) if rule.condition == NONLOCAL_CONDITION]


def rule_count(session) -> int:
    return session.scalar(select(func.count(ChecklistRule.id)))


def simulate_old_database(session) -> None:
    """模拟升级前的库：没有外地规则，也没有 rules_version。"""
    for rule in nonlocal_rules(session):
        session.delete(rule)
    session.execute(delete(AppSetting).where(AppSetting.key == RULES_VERSION_KEY))
    session.commit()


def test_fresh_database_has_rule_and_version(session):
    rules = nonlocal_rules(session)
    assert len(rules) == 1
    assert rules[0].level == "required" and rules[0].hint == NONLOCAL_ORDER_RULE[4]
    assert session.get(AppSetting, RULES_VERSION_KEY).value == str(RULES_VERSION)


def test_sync_appends_rule_once_for_old_database(session):
    simulate_old_database(session)
    before = rule_count(session)

    sync_default_rules(session)
    sync_default_rules(session)

    assert len(nonlocal_rules(session)) == 1
    assert rule_count(session) == before + 1
    assert session.get(AppSetting, RULES_VERSION_KEY).value == str(RULES_VERSION)


def test_sync_does_not_duplicate_existing_rule(session):
    session.execute(delete(AppSetting).where(AppSetting.key == RULES_VERSION_KEY))
    session.commit()
    before = rule_count(session)

    sync_default_rules(session)

    assert rule_count(session) == before
    assert len(nonlocal_rules(session)) == 1


def test_sync_skips_when_version_current_even_if_user_deleted_rule(session):
    for rule in nonlocal_rules(session):
        session.delete(rule)
    session.commit()

    sync_default_rules(session)

    assert nonlocal_rules(session) == []


def test_sync_keeps_user_rules_and_does_not_restore_old_defaults(session):
    office = session.scalar(select(Category.id).where(Category.name == "办公用品"))
    session.execute(delete(ChecklistRule).where(ChecklistRule.category_id == office))
    session.add(ChecklistRule(category_id=None, attachment_kind="other", hint="用户规则"))
    simulate_old_database(session)

    sync_default_rules(session)

    kinds = set(session.scalars(select(ChecklistRule.hint)))
    assert "用户规则" in kinds
    office_rules = session.scalars(select(ChecklistRule).where(ChecklistRule.category_id == office))
    assert list(office_rules) == []


def test_sync_skips_rule_for_missing_category(session, monkeypatch):
    spec = ("不存在的分类", "order", "required", {"amount_gte": 1}, "x")
    monkeypatch.setattr(seed, "RULES_ADDED_IN", {2: (spec,)})
    simulate_old_database(session)
    before = rule_count(session)

    sync_default_rules(session)

    assert rule_count(session) == before


def test_sync_adds_category_rule_by_name(session, monkeypatch):
    spec = ("办公用品", "payment", "suggested", {"amount_gte": 123}, "测试")
    monkeypatch.setattr(seed, "RULES_ADDED_IN", {1: (NONLOCAL_ORDER_RULE,), 2: (spec,)})
    simulate_old_database(session)

    sync_default_rules(session)

    office = session.scalar(select(Category.id).where(Category.name == "办公用品"))
    added = session.scalar(select(ChecklistRule).where(ChecklistRule.hint == "测试"))
    assert added.category_id == office
    assert nonlocal_rules(session) == []  # 版本 1 的规则不补


def test_non_numeric_version_is_treated_as_base(session):
    simulate_old_database(session)
    session.add(AppSetting(key=RULES_VERSION_KEY, value="abc"))
    session.commit()

    sync_default_rules(session)

    assert len(nonlocal_rules(session)) == 1
