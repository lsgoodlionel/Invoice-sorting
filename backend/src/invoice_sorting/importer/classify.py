"""分类建议：① 商品记忆 → ② 商家记忆 → ③ 税收分类简称 → ④ 摘要/销售方关键词 → ⑤ 其他。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.db.models import Category, ItemMemory, MerchantMemory
from invoice_sorting.expenses.service import normalize_item_name

OTHER_CATEGORY_NAME = "其他"


def _active_categories(session: Session) -> list[Category]:
    query = (
        select(Category).where(Category.archived.is_(False)).order_by(Category.sort, Category.id)
    )
    return list(session.scalars(query))


def _longest_keyword_match(categories: list[Category], text: str) -> Category | None:
    """返回包含最长关键词的分类；长度相同时按分类排序靠前者。"""
    haystack = (text or "").strip().lower()
    if not haystack:
        return None
    best: Category | None = None
    best_length = 0
    for category in categories:
        for keyword in category.keywords or []:
            needle = keyword.strip().lower()
            if needle and needle in haystack and len(needle) > best_length:
                best, best_length = category, len(needle)
    return best


def _from_memory(
    session: Session, seller_name: str, item_summary: str, active_ids: set[int]
) -> int | None:
    lookups = (
        (ItemMemory, normalize_item_name(item_summary)),
        (MerchantMemory, (seller_name or "").strip()),
    )
    for model, key in lookups:
        memory = session.get(model, key) if key else None
        if memory is not None and memory.category_id in active_ids:
            return memory.category_id
    return None


def suggest_category(
    session: Session, seller_name: str, item_summary: str, tax_category: str
) -> int | None:
    """按优先级给出分类 id；归档分类不参与，连“其他”也不可用时返回 None。"""
    categories = _active_categories(session)
    active_ids = {item.id for item in categories}
    remembered = _from_memory(session, seller_name, item_summary, active_ids)
    if remembered is not None:
        return remembered
    for text in (tax_category, item_summary, seller_name):
        matched = _longest_keyword_match(categories, text)
        if matched is not None:
            return matched.id
    other = next((item for item in categories if item.name == OTHER_CATEGORY_NAME), None)
    return other.id if other is not None else None
