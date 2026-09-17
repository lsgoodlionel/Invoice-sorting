"""分类建议（蓝图 4.1）：① 商家记忆 → ② 税收分类简称 → ③ 摘要/销售方关键词 → ④ 其他。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.db.models import Category, MerchantMemory

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


def _from_memory(session: Session, seller_name: str, active_ids: set[int]) -> int | None:
    name = (seller_name or "").strip()
    if not name:
        return None
    memory = session.get(MerchantMemory, name)
    if memory is None or memory.category_id not in active_ids:
        return None
    return memory.category_id


def suggest_category(
    session: Session, seller_name: str, item_summary: str, tax_category: str
) -> int | None:
    """按优先级给出分类 id；归档分类不参与，连“其他”也不可用时返回 None。"""
    categories = _active_categories(session)
    remembered = _from_memory(session, seller_name, {item.id for item in categories})
    if remembered is not None:
        return remembered
    for text in (tax_category, item_summary, seller_name):
        matched = _longest_keyword_match(categories, text)
        if matched is not None:
            return matched.id
    other = next((item for item in categories if item.name == OTHER_CATEGORY_NAME), None)
    return other.id if other is not None else None
