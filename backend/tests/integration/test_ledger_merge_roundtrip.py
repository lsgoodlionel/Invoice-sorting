"""合并导入的往返与幂等（账本搬迁设计 4）：导出 → 并入空账本 → 再并一次 → 并入部分重叠的账本。"""

import json
import zipfile
from datetime import date

import pytest
from sqlalchemy import select

from invoice_sorting.config import PACKAGES_DIRNAME
from invoice_sorting.db.models import (
    Attachment,
    Batch,
    Expense,
    ExportRecord,
    InvoiceData,
    StatusEvent,
    User,
)
from invoice_sorting.migration.ledger import LEDGER_NAME
from invoice_sorting.migration.merge import merge_import, preview_merge
from invoice_sorting.migration.merge_apply import IMPORTED_EXPORTS_DIRNAME
from tests.merge_helpers import (
    BARE,
    BATCH_NAME,
    EXTRA,
    INVOICED,
    PERSON,
    SOURCE_NAME,
    SOURCE_SLUG,
    add_invoiced_expense,
    digest_of,
    export_source,
    library_files,
    open_target,
    seed_rich_ledger,
)

TARGET = "merge-target"


@pytest.fixture
def source(app, settings, session, tmp_path):
    seed_rich_ledger(session, settings, tmp_path / "来源")
    return app


def merge(app, archive, slug: str = TARGET):
    return merge_import(app.state.tenants, app.state.control_session_factory, archive, slug)


def preview(app, archive, slug: str = TARGET):
    return preview_merge(app.state.tenants, app.state.control_session_factory, archive, slug)


def test_merge_into_empty_ledger_matches_source(source, tmp_path):
    archive = export_source(source, tmp_path / "包.zip")
    target = open_target(source, TARGET)

    report = merge(source, archive)

    assert digest_of(target) == digest_of(source.state.tenants.get(SOURCE_SLUG))
    records = report.section("records")
    assert (records.added, records.skipped) == (len(INVOICED) + 1, 1)  # 已删除记录不导入
    assert report.section("attachments").added == len(INVOICED) + 2  # 发票 + 订单 + 待归属
    assert report.is_dry_run is False and report.total_added > 0
    source_info = report.to_dict()["source"]
    assert (source_info["tenant"], source_info["exported_by"]) == (SOURCE_NAME, "虚构管理员")
    assert source_info["is_legacy"] is False and source_info["scope"]["records"] == 4


def test_second_merge_is_fully_deduplicated(source, tmp_path):
    archive = export_source(source, tmp_path / "包.zip")
    target = open_target(source, TARGET)
    merge(source, archive)
    before, files_before = digest_of(target), library_files(target.settings)

    again = merge(source, archive)

    assert again.total_added == 0
    assert digest_of(target) == before
    assert library_files(target.settings) == files_before
    assert again.section("records").skipped == len(INVOICED) + 2
    assert any("都已存在" in warning for warning in again.warnings)


def test_merge_into_overlapping_ledger_only_adds_difference(source, settings, session, tmp_path):
    first = export_source(source, tmp_path / "第一次.zip")
    target = open_target(source, TARGET)
    merge(source, first)
    with target.session_factory() as db:
        kept = db.scalars(select(Expense).where(Expense.merchant == INVOICED[0][0])).one()
        kept.note = "本地改过的备注"
        db.commit()
        kept_updated_at = kept.updated_at.replace(tzinfo=None)  # SQLite 读回不带时区
    add_invoiced_expense(session, settings, tmp_path / "来源", EXTRA)
    session.commit()
    second = export_source(source, tmp_path / "第二次.zip")

    report = merge(source, second)

    assert report.section("records").added == 1
    assert report.section("attachments").added == 1
    with target.session_factory() as db:
        merchants = sorted(e.merchant for e in db.scalars(select(Expense)))
        kept = db.scalars(select(Expense).where(Expense.merchant == INVOICED[0][0])).one()
        assert (kept.note, kept.updated_at) == ("本地改过的备注", kept_updated_at)
    expected = sorted([*(spec[0] for spec in INVOICED), BARE[0], EXTRA[0]])
    assert merchants == expected


def test_matching_record_without_invoice_number_is_skipped(source, tmp_path):
    """金额 + 日期 + 商家相同且附件内容相同：视为同一条记录。"""
    archive = export_source(source, tmp_path / "包.zip")
    target = open_target(source, TARGET)
    merge(source, archive)
    with target.session_factory() as db:
        for row in db.scalars(select(InvoiceData)):
            db.delete(row)  # 去掉发票号，只剩“金额 + 日期 + 商家 + 附件”这条规则
        db.commit()

    report = merge(source, archive)

    assert report.section("records").added == 0
    reasons = [item.reason for item in report.section("records").items]
    assert any("金额、日期、商家相同且附件重合" in reason for reason in reasons)


def test_primary_keys_are_reassigned_and_foreign_keys_rewritten(source, tmp_path):
    archive = export_source(source, tmp_path / "包.zip")
    target = open_target(source, TARGET)
    with target.session_factory() as db:  # 目标先占掉一些 id，包内 id 不可能原样可用
        for day in range(1, 8):
            db.add(Expense(spent_on=date(2025, 1, day), amount_cents=day, merchant="虚构本地"))
        db.commit()

    merge(source, archive)

    with target.session_factory() as db:
        imported = list(db.scalars(select(Expense).where(Expense.merchant != "虚构本地")))
        batch = db.scalars(select(Batch)).one()
        person = db.scalars(select(User).where(User.username == PERSON)).one()
        assert min(e.id for e in imported) > 7
        invoiced = {spec[0] for spec in INVOICED}
        assert {e.batch_id for e in imported if e.merchant in invoiced} == {batch.id}
        assert {e.created_by_id for e in imported if e.batch_id} == {person.id}
        assert batch.created_by_id == person.id
        events = list(db.scalars(select(StatusEvent).where(StatusEvent.actor_id.is_not(None))))
        assert {event.actor_id for event in events} == {person.id}
        assert all(db.get(Expense, event.expense_id) is not None for event in events)


def test_files_follow_local_library_naming(source, tmp_path):
    archive = export_source(source, tmp_path / "包.zip")
    target = open_target(source, TARGET)

    merge(source, archive)

    with target.session_factory() as db:
        for item in db.scalars(select(Attachment)):
            path = target.settings.data_dir / item.file_path
            assert path.is_file()
            if item.expense is None:
                assert item.file_path.startswith("文件库/待归属/")
                continue
            assert item.file_path.startswith(f"文件库/{item.expense.folder_path}/")
            assert item.expense.folder_path.endswith(f"_E{item.expense.id:04d}")
            if item.invoice_data is not None:
                assert path.name == f"发票_{item.invoice_data.invoice_no}.pdf"


def test_export_records_are_kept_without_package_zip(source, tmp_path):
    archive = export_source(source, tmp_path / "包.zip")
    target = open_target(source, TARGET)

    report = merge(source, archive)

    with target.session_factory() as db:
        record = db.scalars(select(ExportRecord)).one()
        assert record.file_path.startswith(f"{PACKAGES_DIRNAME}/{IMPORTED_EXPORTS_DIRNAME}/")
        assert not (target.settings.data_dir / record.file_path).exists()
        assert db.get(Batch, record.batch_id).name == BATCH_NAME
    assert not any(target.settings.packages_dir.rglob("*.zip"))
    assert report.section("exports").added == 1


def test_export_writes_ledger_description(source, tmp_path):
    archive = export_source(source, tmp_path / "包.zip")

    with zipfile.ZipFile(archive) as package:
        ledger = json.loads(package.read(LEDGER_NAME).decode("utf-8"))

    assert ledger["kind"] == "ledger"
    assert ledger["source"]["tenant"] == SOURCE_NAME
    assert ledger["source"]["exported_by"] == "虚构管理员"
    assert ledger["source"]["deployment"] == "single"
    assert ledger["scope"] == {
        "records": len(INVOICED) + 1,
        "attachments": len(INVOICED) + 2,
        "batches": 1,
        "from": "2026-09-11",
        "to": "2026-09-14",
    }


def test_preview_matches_real_import(source, tmp_path):
    archive = export_source(source, tmp_path / "包.zip")
    open_target(source, TARGET)

    planned = preview(source, archive)
    done = merge(source, archive)

    assert planned.is_dry_run is True
    assert {k: v.added for k, v in planned.sections.items()} == {
        k: v.added for k, v in done.sections.items()
    }
