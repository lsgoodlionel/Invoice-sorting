"""运行日志配置（设计《日志与故障上报》2 运行日志）。"""

import logging
from pathlib import Path

from invoice_sorting.diagnostics.constants import LOG_BACKUP_COUNT, LOG_MAX_BYTES
from invoice_sorting.diagnostics.logging_setup import (
    HANDLER_MARK,
    configure_logging,
    log_startup_summary,
    resolve_level,
)
from tests.conftest import make_settings
from tests.diagnostics_helpers import FAKE_REPO, FAKE_TOKEN


def test_log_file_is_created_under_data_dir(tmp_path: Path, clean_root) -> None:
    settings = make_settings(tmp_path)

    path = configure_logging(settings)

    assert path == settings.data_dir / "日志" / "app.log"
    logging.getLogger("invoice_sorting").info("启动完成")
    assert "启动完成" in path.read_text(encoding="utf-8")


def test_handler_rotates_by_size(tmp_path: Path, clean_root) -> None:
    configure_logging(make_settings(tmp_path))

    handler = next(item for item in clean_root.handlers if getattr(item, HANDLER_MARK, False))
    assert handler.maxBytes == LOG_MAX_BYTES
    assert handler.backupCount == LOG_BACKUP_COUNT


def test_configure_is_idempotent(tmp_path: Path, clean_root) -> None:
    settings = make_settings(tmp_path)

    configure_logging(settings)
    configure_logging(settings)

    installed = [item for item in clean_root.handlers if getattr(item, HANDLER_MARK, False)]
    assert len(installed) == 1


def test_level_comes_from_settings(tmp_path: Path, clean_root) -> None:
    configure_logging(make_settings(tmp_path, log_level="WARNING"))

    assert clean_root.level == logging.WARNING


def test_unknown_level_falls_back_to_info() -> None:
    assert resolve_level("胡写的级别") == logging.INFO
    assert resolve_level("") == logging.INFO
    assert resolve_level("debug") == logging.DEBUG


def test_secrets_are_scrubbed_before_reaching_the_log_file(tmp_path: Path, clean_root) -> None:
    # Arrange
    path = configure_logging(make_settings(tmp_path))
    logger = logging.getLogger("invoice_sorting.test")

    # Act：模拟某处不小心把整份配置打了出来
    logger.warning("配置：log_token=%s password=%s", FAKE_TOKEN, "hunter2")

    # Assert
    written = path.read_text(encoding="utf-8")
    assert FAKE_TOKEN not in written
    assert "hunter2" not in written
    assert "<已隐去>" in written


def test_startup_summary_has_no_secret(tmp_path: Path, clean_root, caplog) -> None:
    settings = make_settings(tmp_path, log_repo=FAKE_REPO, log_token=FAKE_TOKEN, license_key="abc")

    with caplog.at_level(logging.INFO):
        log_startup_summary(settings)

    assert FAKE_TOKEN not in caplog.text
    assert "abc" not in caplog.text
    assert "诊断包上传已启用" in caplog.text


def test_unwritable_log_dir_does_not_break_startup(tmp_path: Path, clean_root) -> None:
    blocked = tmp_path / "blocked"
    blocked.write_text("我是文件不是目录", encoding="utf-8")

    assert configure_logging(make_settings(tmp_path, data_dir=blocked)) is None
