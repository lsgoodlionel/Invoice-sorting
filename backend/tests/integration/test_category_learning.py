"""手动修改分类后记住“商品 → 分类”；默认关键词升级时合并进已有分类。"""

import pytest
from sqlalchemy import select

from invoice_sorting.db.default_keywords import KEYWORDS_VERSION
from invoice_sorting.db.models import AppSetting, Category, ItemMemory
from invoice_sorting.db.seed import sync_default_keywords
from tests.integration.test_importer_api import confirm, group_payload, sample, upload


@pytest.fixture(autouse=True)
def _isolate_recognition(fake_recognition):
    """凭证识别使用可控的假实现。"""


def category(session, name: str) -> Category:
    return session.scalar(select(Category).where(Category.name == name))


def test_changing_category_remembers_invoice_item(client, session, tmp_path):
    imported = upload(client, sample(tmp_path, "digital_same_line.pdf"))["data"]
    row = imported["groups"][0]
    expense_id = confirm(client, imported["session_id"], group_payload(row)).json()["data"][
        "created"
    ][0]
    low_value = category(session, "低值品").id

    client.patch(f"/api/expenses/{expense_id}", json={"category_id": low_value})

    session.expire_all()
    memory = session.get(ItemMemory, "鼠标")
    assert memory is not None and memory.category_id == low_value


def test_sync_default_keywords_merges_into_existing_categories_once(session):
    office = category(session, "办公用品")
    office.keywords = ["自定义词"]
    session.delete(session.get(AppSetting, "keywords_version"))
    session.commit()

    sync_default_keywords(session)

    session.refresh(office)
    assert "自定义词" in office.keywords
    assert "收纳" in office.keywords
    assert session.get(AppSetting, "keywords_version").value == str(KEYWORDS_VERSION)

    office.keywords = ["自定义词"]  # 用户删掉默认关键词后，同版本不再加回
    session.commit()
    sync_default_keywords(session)
    session.refresh(office)
    assert office.keywords == ["自定义词"]


def test_confirm_with_user_changed_category_remembers_item(client, session, tmp_path):
    from invoice_sorting.db.models import MerchantMemory

    imported = upload(client, sample(tmp_path, "digital_same_line.pdf"))["data"]
    group = imported["groups"][0]
    office = category(session, "办公用品").id
    assert group["summary"]["category_id"] != office

    confirm(client, imported["session_id"], group_payload(group, category_id=office))

    session.expire_all()
    assert session.get(ItemMemory, "鼠标").category_id == office
    assert session.get(MerchantMemory, "上海示例科技有限公司").category_id == office


def test_patch_with_unchanged_category_does_not_remember(client, session, tmp_path):
    imported = upload(client, sample(tmp_path, "digital_same_line.pdf"))["data"]
    group = imported["groups"][0]
    created = confirm(client, imported["session_id"], group_payload(group)).json()["data"]
    expense_id = created["created"][0]
    current = client.get(f"/api/expenses/{expense_id}").json()["data"]["category_id"]

    client.patch(f"/api/expenses/{expense_id}", json={"category_id": current, "note": "改备注"})

    session.expire_all()
    assert session.get(ItemMemory, "鼠标") is None


def test_memory_cleanup_runs_once(session):
    from invoice_sorting.db.models import MerchantMemory
    from invoice_sorting.db.seed import MEMORY_VERSION_KEY, reset_polluted_memory

    office = category(session, "办公用品").id
    session.add(ItemMemory(item_name="旧商品", category_id=office))
    session.add(MerchantMemory(seller_name="旧商家", category_id=office))
    session.query(AppSetting).filter(AppSetting.key == MEMORY_VERSION_KEY).delete()
    session.commit()

    reset_polluted_memory(session)
    assert session.scalars(select(ItemMemory)).all() == []
    assert session.scalars(select(MerchantMemory)).all() == []

    session.add(ItemMemory(item_name="新商品", category_id=office))
    session.commit()
    reset_polluted_memory(session)
    assert session.get(ItemMemory, "新商品") is not None
