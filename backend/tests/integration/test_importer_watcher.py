"""收件箱监听：自动新建/挂接/留待归属、无法处理目录、忽略临时文件、线程启动与停止。"""

import shutil
import time
from datetime import date
from pathlib import Path

from sqlalchemy import select

from invoice_sorting.db.models import Attachment, Expense, InvoiceData
from invoice_sorting.expenses.service import create_expense
from invoice_sorting.importer import auto_confirm, watcher
from invoice_sorting.importer.watcher import process_inbox_once, start_inbox_watcher
from tests.conftest import FIXTURES_DIR

INVOICES = FIXTURES_DIR / "invoices"
WAIT_SECONDS = 10


def drop(settings, name: str, as_name: str | None = None) -> Path:
    settings.inbox_dir.mkdir(parents=True, exist_ok=True)
    target = settings.inbox_dir / (as_name or name)
    shutil.copyfile(INVOICES / name, target)
    return target


def xml_without_amount_and_date(settings) -> Path:
    text = (INVOICES / "digital_invoice.xml").read_text(encoding="utf-8")
    for tag in ("TotalTax-includedAmount", "RequestTime", "IssueTime", "TotalAmWithoutTax"):
        start = text.index(f"<{tag}>")
        end = text.index(f"</{tag}>") + len(f"</{tag}>")
        text = text[:start] + text[end:]
    target = settings.inbox_dir / "缺金额.xml"
    target.write_text(text, encoding="utf-8")
    return target


def expenses(session) -> list[Expense]:
    session.expire_all()
    return list(session.scalars(select(Expense).order_by(Expense.id)))


def test_process_inbox_auto_confirms_and_sorts_failures(app, session, settings):
    spent = create_expense(
        session, settings, spent_on=date(2026, 9, 11), amount_cents=13950, merchant="铁路"
    )
    session.commit()
    drop(settings, "digital_same_line.pdf")
    drop(settings, "rail_ticket.pdf")
    drop(settings, "not_invoice.pdf")
    xml_without_amount_and_date(settings)
    (settings.inbox_dir / "说明.txt").write_text("hello", encoding="utf-8")
    (settings.inbox_dir / ".DS_Store").write_bytes(b"x")
    (settings.inbox_dir / "下载中.pdf.crdownload").write_bytes(b"%PDF-")
    (settings.inbox_dir / "子目录").mkdir()

    count = process_inbox_once(app, interval=0)

    assert count == 5
    remaining = sorted(path.name for path in settings.inbox_dir.iterdir())
    assert remaining == [".DS_Store", "下载中.pdf.crdownload", "子目录", "无法处理"]
    failed_dir = settings.inbox_dir / "无法处理"
    assert (failed_dir / "说明.txt").is_file()
    assert "不支持的文件类型" in (failed_dir / "说明.txt.txt").read_text(encoding="utf-8")

    rows = expenses(session)
    assert len(rows) == 2
    assert rows[0].id == spent.id and rows[0].status == "invoiced"
    created = rows[1]
    assert (created.amount_cents, created.merchant) == (96000, "上海示例科技有限公司")
    assert created.status == "invoiced"
    pending = session.scalars(select(Attachment).where(Attachment.expense_id.is_(None))).all()
    assert sorted(item.original_name for item in pending) == ["not_invoice.pdf", "缺金额.xml"]
    xml = next(item for item in pending if item.original_name == "缺金额.xml")
    assert xml.invoice_data is not None and xml.invoice_data.confirmed is False


def test_duplicate_source_is_removed(app, settings):
    drop(settings, "not_invoice.pdf")
    process_inbox_once(app, interval=0)
    drop(settings, "not_invoice.pdf", "副本.pdf")

    assert process_inbox_once(app, interval=0) == 1

    assert list(settings.inbox_dir.iterdir()) == []


def test_failed_names_do_not_collide(app, settings):
    for _ in range(2):
        (settings.inbox_dir / "坏.txt").write_text("x", encoding="utf-8")
        process_inbox_once(app, interval=0)

    names = sorted(path.name for path in (settings.inbox_dir / "无法处理").iterdir())
    assert names == ["坏.txt", "坏.txt.txt", "坏_2.txt", "坏_2.txt.txt"]


def test_unstable_file_is_left_for_next_round(app, settings, monkeypatch):
    growing = drop(settings, "not_invoice.pdf")
    monkeypatch.setattr(watcher.time, "sleep", lambda _s: growing.write_bytes(b"%PDF-1.4 more"))

    assert process_inbox_once(app, interval=1) == 0
    assert growing.exists()


def test_empty_inbox_does_not_sleep(app, settings, monkeypatch):
    monkeypatch.setattr(watcher.time, "sleep", lambda _s: (_ for _ in ()).throw(AssertionError))
    shutil.rmtree(settings.inbox_dir)

    assert process_inbox_once(app) == 0


def test_unexpected_error_moves_file_to_failed_dir(app, settings, monkeypatch):
    source = drop(settings, "not_invoice.pdf")

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(watcher, "import_files", boom)

    assert process_inbox_once(app, interval=0) == 1
    assert not source.exists()
    reason = (settings.inbox_dir / "无法处理" / "not_invoice.pdf.txt").read_text(encoding="utf-8")
    assert "导入时发生意外错误" in reason


def test_auto_confirm_failure_keeps_invoice_pending(app, session, settings, monkeypatch):
    source = drop(settings, "digital_same_line.pdf")

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(auto_confirm, "confirm_rows", boom)

    assert process_inbox_once(app, interval=0) == 1
    assert not source.exists()
    assert expenses(session) == []
    invoice = session.scalar(select(InvoiceData))
    assert invoice.confirmed is False and invoice.attachment.expense_id is None


def wait_until(predicate) -> bool:
    deadline = time.monotonic() + WAIT_SECONDS
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_watcher_processes_existing_and_new_files(app, session, settings, monkeypatch):
    monkeypatch.setattr(watcher, "STABLE_INTERVAL_SECONDS", 0.05)
    drop(settings, "digital_same_line.pdf")

    handle = start_inbox_watcher(app)
    try:
        assert wait_until(lambda: not any(settings.inbox_dir.iterdir()))
        drop(settings, "rail_ticket.pdf")
        assert wait_until(lambda: not any(settings.inbox_dir.iterdir()))
    finally:
        handle.stop()

    assert len(expenses(session)) == 2
    handle.stop()


def test_watcher_survives_processing_errors(app, settings, monkeypatch):
    monkeypatch.setattr(watcher, "STABLE_INTERVAL_SECONDS", 0.05)
    calls: list[int] = []

    def flaky(_app, interval=0):
        calls.append(1)
        raise RuntimeError("boom")

    monkeypatch.setattr(watcher, "process_inbox_once", flaky)
    handle = start_inbox_watcher(app)
    try:
        assert wait_until(lambda: len(calls) >= 1)
        (settings.inbox_dir / "新文件.pdf").write_bytes(b"%PDF-1.4")
        assert wait_until(lambda: len(calls) >= 2)
    finally:
        handle.stop()
