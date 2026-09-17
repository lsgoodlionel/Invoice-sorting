"""分类建议优先级：商品记忆 → 文件名 → 税收分类 → 商家记忆（非电商平台） → 关键词 → 其他。"""

from sqlalchemy import select

from invoice_sorting.db.models import Category
from invoice_sorting.expenses.service import remember_item_category, remember_merchant_category
from invoice_sorting.importer.classify import suggest_category


def category_id(session, name: str) -> int:
    return session.scalar(select(Category.id).where(Category.name == name))


def test_merchant_memory_used_when_tax_category_does_not_match(session):
    remember_merchant_category(session, "上海示例科技有限公司", category_id(session, "设备"))

    result = suggest_category(session, " 上海示例科技有限公司 ", "鼠标", "")

    assert result == category_id(session, "设备")


def test_tax_category_beats_merchant_memory(session):
    # 用户反馈：同一商家卖图书也卖电脑配件，商家记忆不能盖过发票上的 *印刷品*
    remember_merchant_category(session, "上海示例科技有限公司", category_id(session, "易耗品"))

    result = suggest_category(session, "上海示例科技有限公司", "系统之美", "印刷品")

    assert result == category_id(session, "图书")


def test_marketplace_sellers_are_not_remembered_or_used(session):
    remember_merchant_category(session, "上海圆迈贸易有限公司", category_id(session, "易耗品"))

    result = suggest_category(session, "上海圆迈贸易有限公司", "未知商品", "")

    assert result == category_id(session, "其他")


def test_filename_category_reflects_user_intent_before_tax_category(session):
    office = category_id(session, "办公用品")
    books = category_id(session, "图书")

    # 用户把电池命名为“办公-…”：以文件名意图为准
    assert (
        suggest_category(session, "某店", "7号电池", "电池", filename_category_id=office) == office
    )
    # 没有文件名分类词时按税收分类
    assert suggest_category(session, "某店", "系统之美", "印刷品") == books


def test_explain_category_reports_basis(session):
    from invoice_sorting.importer.classify import explain_category

    suggestion = explain_category(session, "上海圆迈贸易有限公司", "系统之美", "印刷品")

    assert suggestion.category_id == category_id(session, "图书")
    assert suggestion.basis == "发票税收分类：印刷品"


def test_memory_pointing_to_archived_category_is_ignored(session):
    equipment = session.get(Category, category_id(session, "设备"))
    remember_merchant_category(session, "某商家", equipment.id)
    equipment.archived = True
    session.flush()

    result = suggest_category(session, "某商家", "", "计算机配套产品")

    assert result == category_id(session, "易耗品")


def test_tax_category_prefers_longest_keyword(session):
    # “计算机配套产品”（易耗品）比“计算机”（设备）更长
    result = suggest_category(session, "无关商家", "无关摘要", "计算机配套产品")

    assert result == category_id(session, "易耗品")


def test_tax_category_before_summary_keywords(session):
    result = suggest_category(session, "", "打印纸", "餐饮服务")

    assert result == category_id(session, "餐饮会议")


def test_summary_keyword_when_tax_category_unmatched(session):
    result = suggest_category(session, "某某公司", "移动硬盘等2项", "未知分类")

    assert result == category_id(session, "低值品")


def test_seller_keyword_used_when_summary_unmatched(session):
    result = suggest_category(session, "中国铁路", "上海虹桥-南京南 G7", "")

    assert result == category_id(session, "差旅交通")


def test_keyword_match_is_case_insensitive(session):
    result = suggest_category(session, "", "u盘 64G", "")

    assert result == category_id(session, "低值品")


def test_archived_category_keywords_do_not_participate(session):
    session.get(Category, category_id(session, "低值品")).archived = True
    session.flush()

    result = suggest_category(session, "", "移动硬盘", "")

    assert result == category_id(session, "其他")


def test_falls_back_to_other(session):
    assert suggest_category(session, "无名", "无法归类的东西", "") == category_id(session, "其他")


def test_returns_none_when_other_is_archived(session):
    session.get(Category, category_id(session, "其他")).archived = True
    session.flush()

    assert suggest_category(session, "无名", "无法归类", "") is None


# ---- 实际使用反馈：收纳盒（*日用杂品*）应归入办公用品；手动改分类后要按商品记住 ----


def test_storage_box_with_daily_goods_tax_category_is_office_supplies(session):
    result = suggest_category(session, "吱二(上海)家居用品有限公司", "收纳盒", "日用杂品")

    assert result == category_id(session, "办公用品")


def test_item_memory_beats_merchant_memory_and_keywords(session):
    remember_merchant_category(session, "综合商城", category_id(session, "易耗品"))
    remember_item_category(session, "收纳盒等2项", category_id(session, "低值品"))

    result = suggest_category(session, "综合商城", "收纳盒", "日用杂品")

    assert result == category_id(session, "低值品")


def test_item_memory_normalizes_summary_suffix(session):
    remember_item_category(session, " 桌面收纳架 ", category_id(session, "办公用品"))

    result = suggest_category(session, "新商家", "桌面收纳架等3项", "")

    assert result == category_id(session, "办公用品")
