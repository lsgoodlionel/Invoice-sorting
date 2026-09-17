"""收件箱监听（蓝图 5.1）：文件稳定后自动导入并确认；失败文件移入“无法处理”并写说明。"""

import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session, sessionmaker
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from invoice_sorting.config import Settings
from invoice_sorting.db.models import now
from invoice_sorting.importer.confirm import confirm_rows
from invoice_sorting.importer.schemas import ConfirmRow
from invoice_sorting.importer.service import ImportResult, ImportRow, import_files

logger = logging.getLogger(__name__)

FAILED_DIRNAME = "无法处理"
TEMP_SUFFIXES = (".crdownload", ".part", ".tmp", ".download")
STABLE_INTERVAL_SECONDS = 1.0
POLL_SECONDS = 5.0
JOIN_TIMEOUT_SECONDS = 5.0
UNKNOWN_MERCHANT = "未知商家"
UNEXPECTED_ERROR = "导入时发生意外错误，请手工导入"


def _is_candidate(path: Path) -> bool:
    name = path.name
    if name.startswith(".") or name.lower().endswith(TEMP_SUFFIXES):
        return False
    return path.is_file()


def _size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


def _stable_files(inbox: Path, interval: float) -> list[Path]:
    """间隔 interval 秒两次检查大小不变的文件（不递归）。"""
    if not inbox.is_dir():
        return []
    first = {path: _size(path) for path in sorted(inbox.iterdir()) if _is_candidate(path)}
    if not first:
        return []
    if interval > 0:
        time.sleep(interval)
    return [path for path, size in first.items() if size is not None and _size(path) == size]


def _auto_row(row: ImportRow) -> ConfirmRow | None:
    """有匹配 → 挂接；金额与日期都识别到 → 新建；否则留在待归属。"""
    suggestion = row.suggestion
    common = {
        "row_id": row.row_id,
        "spent_on": suggestion.spent_on,
        "amount_cents": suggestion.amount_cents,
        "merchant": suggestion.merchant or UNKNOWN_MERCHANT,
        "summary": suggestion.summary,
        "category_id": suggestion.category_id,
    }
    if row.match is not None:
        return ConfirmRow(action="attach", expense_id=row.match.id, **common)
    if suggestion.amount_cents is not None and suggestion.spent_on is not None:
        return ConfirmRow(action="create", **common)
    return None


def _auto_confirm(session: Session, settings: Settings, result: ImportResult) -> None:
    rows = [confirm for confirm in map(_auto_row, result.rows) if confirm is not None]
    if not rows:
        return
    refs = {row.row_id: row.attachment.id for row in result.rows}
    try:
        confirm_rows(session, settings, refs, rows)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("收件箱自动确认失败，发票保留在待归属")


def _import_path(factory: sessionmaker[Session], settings: Settings, path: Path) -> str | None:
    """导入单个文件；返回失败原因，成功（含重复）返回 None。"""
    with factory() as session:
        result = import_files(session, settings, [(path, path.name)])
        session.commit()
        if result.failed:
            return next(iter(result.failed.values()))
        _auto_confirm(session, settings, result)
    return None


def _free_name(directory: Path, name: str) -> Path:
    candidate = directory / name
    stem, suffix = Path(name).stem, Path(name).suffix
    index = 2
    while candidate.exists() or Path(f"{candidate}.txt").exists():
        candidate = directory / f"{stem}_{index}{suffix}"
        index += 1
    return candidate


def _move_to_failed(settings: Settings, path: Path, reason: str) -> None:
    failed_dir = settings.inbox_dir / FAILED_DIRNAME
    failed_dir.mkdir(parents=True, exist_ok=True)
    target = _free_name(failed_dir, path.name)
    shutil.move(path, target)
    note = f"{path.name}\n时间：{now():%Y-%m-%d %H:%M:%S}\n原因：{reason}\n"
    Path(f"{target}.txt").write_text(note, encoding="utf-8")


def _process_path(app: Any, path: Path) -> None:
    settings: Settings = app.state.settings
    try:
        reason = _import_path(app.state.session_factory, settings, path)
    except Exception:
        logger.exception("收件箱文件导入失败：%s", path.name)
        reason = UNEXPECTED_ERROR
    try:
        if reason is None:
            path.unlink(missing_ok=True)
        else:
            _move_to_failed(settings, path, reason)
    except OSError:
        logger.exception("整理收件箱文件失败：%s", path.name)


def process_inbox_once(app: Any, interval: float | None = None) -> int:
    """处理收件箱中已稳定的文件，返回处理的文件数。"""
    settings: Settings = app.state.settings
    wait = STABLE_INTERVAL_SECONDS if interval is None else interval
    ready = _stable_files(settings.inbox_dir, wait)
    for path in ready:
        _process_path(app, path)
    return len(ready)


class _WakeHandler(FileSystemEventHandler):
    def __init__(self, wake: threading.Event) -> None:
        self._wake = wake

    def on_any_event(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._wake.set()


class InboxWatcher:
    """watchdog 事件唤醒 + 定时轮询兜底；在独立线程中处理，异常只记录日志。"""

    def __init__(self, app: Any, poll_seconds: float = POLL_SECONDS) -> None:
        self._app = app
        self._poll_seconds = poll_seconds
        self._wake = threading.Event()
        self._stopped = threading.Event()
        self._observer: Any = None
        self._thread = threading.Thread(target=self._run, name="inbox-watcher", daemon=True)

    def start(self) -> "InboxWatcher":
        inbox = self._app.state.settings.inbox_dir
        inbox.mkdir(parents=True, exist_ok=True)
        try:
            observer = Observer()
            observer.schedule(_WakeHandler(self._wake), str(inbox), recursive=False)
            observer.start()
            self._observer = observer
        except Exception:
            logger.exception("收件箱文件事件监听启动失败，改为定时轮询")
        self._wake.set()  # 启动时先处理一次已有文件
        self._thread.start()
        return self

    def _run(self) -> None:
        while not self._stopped.is_set():
            self._wake.wait(timeout=self._poll_seconds)
            if self._stopped.is_set():
                return
            self._wake.clear()
            try:
                process_inbox_once(self._app, STABLE_INTERVAL_SECONDS)
            except Exception:
                logger.exception("处理收件箱失败")

    def stop(self) -> None:
        if self._stopped.is_set():
            return
        self._stopped.set()
        self._wake.set()
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=JOIN_TIMEOUT_SECONDS)
        if self._thread.is_alive():
            self._thread.join(timeout=JOIN_TIMEOUT_SECONDS)


def start_inbox_watcher(app: Any) -> InboxWatcher:
    return InboxWatcher(app).start()
