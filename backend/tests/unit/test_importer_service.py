"""导入服务单元测试：建议字段与提示、意外异常隔离、文件操作撤销。"""

import shutil
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select

from invoice_sorting.db.models import Attachment, InvoiceData
from invoice_sorting.importer import service
from invoice_sorting.importer.journal import FsJournal
from invoice_sorting.importer.service import import_files
from invoice_sorting.importer.suggestions import (
    BUYER_MISMATCH_WARNING,
    MISSING_AMOUNT_WARNING,
    MISSING_DATE_WARNING,
    MISSING_NUMBER_WARNING,
    MISSING_SELLER_WARNING,
    RAW_TEXT_LIMIT,
    build_warnings,
    invoice_data_from,
    suggested_spent_on,
)
from invoice_sorting.parsers import ParsedInvoice
from tests.conftest import FIXTURES_DIR


@pytest.fixture(autouse=True)
def _isolate_recognition(fake_recognition):
    """凭证识别使用可控的假实现。"""


INVOICES = FIXTURES_DIR / "invoices"

PARSED = ParsedInvoice(
    invoice_no="1",
    issued_on=date(2026, 9, 1),
    total_cents=100,
    tax_cents=None,
    amount_cents=None,
    seller_name="甲公司",
    seller_tax_id="",
    buyer_name="华东师范大学",
    buyer_tax_id="12310000EXAMPLE001",
    item_summary="",
    tax_category="",
    invoice_type="数电发票",
    parser="test",
    warnings=("大小写金额不一致",),
    raw_text="x" * (RAW_TEXT_LIMIT + 10),
)


def test_missing_fields_produce_warnings():
    parsed = replace(
        PARSED, invoice_no=None, issued_on=None, total_cents=None, seller_name="", warnings=()
    )

    warnings = build_warnings(parsed, invoice_data_from(parsed), None)

    assert warnings == [
        MISSING_AMOUNT_WARNING,
        MISSING_DATE_WARNING,
        MISSING_SELLER_WARNING,
        MISSING_NUMBER_WARNING,
    ]


def test_buyer_mismatch_by_tax_id_only():
    warnings = build_warnings(PARSED, invoice_data_from(PARSED), ("", "99999"))

    assert warnings == ["大小写金额不一致", BUYER_MISMATCH_WARNING]
    assert build_warnings(PARSED, invoice_data_from(PARSED), ("华东师范大学", "")) == [
        "大小写金额不一致"
    ]


def test_raw_text_is_truncated():
    assert len(invoice_data_from(PARSED).raw_text) == RAW_TEXT_LIMIT


def test_travel_date_preferred_and_invalid_falls_back():
    assert suggested_spent_on(replace(PARSED, travel={"date": "2026-09-20"})) == date(2026, 9, 20)
    assert suggested_spent_on(replace(PARSED, travel={"date": "bad"})) == date(2026, 9, 1)
    assert suggested_spent_on(replace(PARSED, travel={})) == date(2026, 9, 1)


def test_unexpected_error_discards_file_and_continues(session, settings, tmp_path, monkeypatch):
    first = tmp_path / "a.pdf"
    second = tmp_path / "b.pdf"
    shutil.copyfile(INVOICES / "digital_same_line.pdf", first)
    shutil.copyfile(INVOICES / "digital_multiline.pdf", second)
    original = service.build_warnings
    calls = {"count": 0}

    def flaky(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("boom")
        return original(*args, **kwargs)

    monkeypatch.setattr(service, "build_warnings", flaky)

    result = import_files(session, settings, [(first, "a.pdf"), (second, "b.pdf")])

    assert result.errors == [{"original_name": "a.pdf", "error": service.UNEXPECTED_ERROR}]
    assert result.failed == {0: service.UNEXPECTED_ERROR}
    assert [a.original_name for group in result.groups for a in group.attachments] == ["b.pdf"]
    assert [item.original_name for item in session.scalars(select(Attachment))] == ["b.pdf"]
    assert session.scalar(select(InvoiceData.invoice_no)) == "26312000000987654321"
    assert len(list((settings.library_dir / "待归属").iterdir())) == 1


def test_journal_undo_moves_back_and_removes_empty_dirs(tmp_path: Path):
    source = tmp_path / "a" / "file.txt"
    source.parent.mkdir()
    source.write_text("x", encoding="utf-8")
    created = tmp_path / "new"
    created.mkdir()
    destination = created / "file.txt"
    journal = FsJournal()
    journal.created_dir(created)
    shutil.move(source, destination)
    journal.moved(source, destination)
    journal.moved(destination, destination)

    journal.undo()

    assert source.is_file()
    assert not created.exists()


def test_journal_undo_logs_errors(tmp_path: Path, monkeypatch, caplog):
    destination = tmp_path / "dst"
    destination.write_text("x", encoding="utf-8")
    journal = FsJournal()
    journal.moved(tmp_path / "src", destination)

    def fail(*_args):
        raise OSError("denied")

    monkeypatch.setattr("invoice_sorting.importer.journal.shutil.move", fail)
    journal.undo()

    assert "撤销文件操作失败" in caplog.text


@pytest.mark.parametrize("name", ["a.crdownload", ".hidden", "b.PART", "c.tmp"])
def test_watcher_ignores_temporary_names(tmp_path: Path, name: str):
    from invoice_sorting.importer.watcher import _is_candidate

    path = tmp_path / name
    path.write_text("x", encoding="utf-8")

    assert _is_candidate(path) is False
