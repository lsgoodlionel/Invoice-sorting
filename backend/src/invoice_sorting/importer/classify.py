"""分类建议，优先级从高到低：

① 商品记忆（仅来自用户亲手修改）
② 文件名分类词（如“图书-…”“办公-…”，代表用户整理文件时的明确意图）
③ 发票税收分类简称（如 *印刷品* → 图书，客观且不受商家影响）
④ 商家记忆（京东、圆迈等综合电商平台除外，它们什么都卖）
⑤ 商品名称、销售方关键词（取最长命中）
⑥ 其他
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.common.platforms import is_marketplace_seller
from invoice_sorting.db.models import Category, ItemMemory, MerchantMemory
from invoice_sorting.expenses.service import normalize_item_name

OTHER_CATEGORY_NAME = "其他"


@dataclass(frozen=True)
class CategorySuggestion:
    category_id: int | None
    basis: str  # 中文依据，如“发票税收分类：印刷品”


def _active_categories(session: Session) -> list[Category]:
    query = (
        select(Category).where(Category.archived.is_(False)).order_by(Category.sort, Category.id)
    )
    return list(session.scalars(query))


def _longest_keyword_match(categories: list[Category], text: str) -> tuple[Category, str] | None:
    """返回包含最长关键词的分类与命中的关键词；长度相同时按分类排序靠前者。"""
    haystack = (text or "").strip().lower()
    if not haystack:
        return None
    best: tuple[Category, str] | None = None
    for category in categories:
        for keyword in category.keywords or []:
            needle = keyword.strip().lower()
            if needle and needle in haystack and (best is None or len(needle) > len(best[1])):
                best = (category, keyword.strip())
    return best


def _memory(session: Session, model: type, key: str, active_ids: set[int]) -> int | None:
    memory = session.get(model, key) if key else None
    if memory is not None and memory.category_id in active_ids:
        return memory.category_id
    return None


def explain_category(
    session: Session,
    seller_name: str,
    item_summary: str,
    tax_category: str,
    filename_category_id: int | None = None,
) -> CategorySuggestion:
    """按优先级给出分类与依据；归档分类不参与，连“其他”也不可用时 category_id 为 None。"""
    categories = _active_categories(session)
    active_ids = {category.id for category in categories}
    remembered = _memory(session, ItemMemory, normalize_item_name(item_summary), active_ids)
    if remembered is not None:
        return CategorySuggestion(remembered, "商品记忆（曾手动修改）")
    if filename_category_id in active_ids:
        return CategorySuggestion(filename_category_id, "文件名分类词")
    matched = _longest_keyword_match(categories, tax_category)
    if matched is not None:
        return CategorySuggestion(matched[0].id, f"发票税收分类：{tax_category.strip()}")
    seller = (seller_name or "").strip()
    if not is_marketplace_seller(seller):
        remembered = _memory(session, MerchantMemory, seller, active_ids)
        if remembered is not None:
            return CategorySuggestion(remembered, "商家记忆")
    for text in (item_summary, seller_name):
        matched = _longest_keyword_match(categories, text)
        if matched is not None:
            return CategorySuggestion(matched[0].id, f"关键词：{matched[1]}")
    other = next((item for item in categories if item.name == OTHER_CATEGORY_NAME), None)
    return CategorySuggestion(other.id if other is not None else None, "未匹配到规则")


def suggest_category(
    session: Session,
    seller_name: str,
    item_summary: str,
    tax_category: str,
    filename_category_id: int | None = None,
) -> int | None:
    suggestion = explain_category(
        session, seller_name, item_summary, tax_category, filename_category_id
    )
    return suggestion.category_id
