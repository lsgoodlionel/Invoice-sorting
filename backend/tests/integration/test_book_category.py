"""新增“图书”分类：新库默认包含；旧库启动时补上分类、关键词与凭证规则。"""

from sqlalchemy import select

from invoice_sorting.db.models import AppSetting, Category, ChecklistRule
from invoice_sorting.db.seed import sync_default_keywords, sync_default_rules
from invoice_sorting.importer.classify import suggest_category


def category(session, name: str) -> Category | None:
    return session.scalar(select(Category).where(Category.name == name))


def book_rules(session, book_id: int) -> set[tuple[str, str]]:
    rules = session.scalars(select(ChecklistRule).where(ChecklistRule.category_id == book_id))
    return {(rule.attachment_kind, rule.level) for rule in rules}


def test_new_database_has_book_category_with_rules(session):
    book = category(session, "图书")

    assert book is not None
    assert "印刷品" in book.keywords
    assert ("order", "required") in book_rules(session, book.id)


def test_books_invoice_with_printed_matter_tax_category_is_book(session):
    result = suggest_category(session, "上海圆迈贸易有限公司", "系统之美", "印刷品")

    assert result == category(session, "图书").id


def test_existing_database_gets_book_category_once(session):
    book = category(session, "图书")
    for rule in session.scalars(select(ChecklistRule).where(ChecklistRule.category_id == book.id)):
        session.delete(rule)
    session.flush()
    session.delete(book)
    printing = category(session, "印刷快递")
    printing.keywords = [*printing.keywords, "印刷品"]
    for key in ("keywords_version", "rules_version"):
        session.merge(AppSetting(key=key, value="2"))
    session.commit()

    sync_default_keywords(session)
    sync_default_rules(session)
    sync_default_keywords(session)
    sync_default_rules(session)

    books = session.scalars(select(Category).where(Category.name == "图书")).all()
    assert len(books) == 1
    assert "印刷品" not in category(session, "印刷快递").keywords
    assert ("order", "required") in book_rules(session, books[0].id)
