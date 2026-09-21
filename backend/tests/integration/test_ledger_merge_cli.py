"""命令行合并导入（账本搬迁设计 6）：默认 merge、--dry-run 只预览、退出码区分校验失败与导入失败。"""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from invoice_sorting import main
from invoice_sorting.migration import merge_apply_records
from tests.merge_helpers import INVOICED, export_source, open_target, seed_rich_ledger

TARGET = "cli-merge"
EXPECTED_RECORDS = len(INVOICED) + 1  # 已删除的那条不导入


@pytest.fixture
def env(app, settings, session, tmp_path, monkeypatch):
    """虚构来源账本 + 已开通的空目标账套，命令行与夹具指向同一数据目录。"""
    seed_rich_ledger(session, settings, tmp_path / "来源")
    open_target(app, TARGET)
    monkeypatch.setenv("INVOICE_SORTING_DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("INVOICE_SORTING_WATCH_INBOX", "false")
    return export_source(app, tmp_path / "包.zip")


def _records(settings) -> int:
    db_path = settings.data_dir / "tenants" / TARGET / "invoice.db"
    with closing(sqlite3.connect(db_path)) as conn:
        return conn.execute("select count(*) from expense").fetchone()[0]


def _run(archive: Path, *extra: str) -> None:
    main.run(["import-tenant", "--in", str(archive), *extra])


def _exit_code(archive: Path, *extra: str) -> int:
    with pytest.raises(SystemExit) as exited:
        _run(archive, *extra)
    return exited.value.code


def test_merge_is_the_default_mode(env, settings, capsys):
    _run(env, "--slug", TARGET)

    printed = capsys.readouterr().out
    assert f"合并导入完成：账套 {TARGET}" in printed
    assert f"记录：新增 {EXPECTED_RECORDS}、跳过 1、冲突 0、失败 0" in printed
    assert _records(settings) == EXPECTED_RECORDS


def test_dry_run_prints_preview_without_writing(env, settings, capsys):
    _run(env, "--slug", TARGET, "--dry-run")

    printed = capsys.readouterr().out
    assert "预览（未写入任何数据）" in printed
    assert f"新增 {EXPECTED_RECORDS}" in printed
    assert _records(settings) == 0


def test_merging_own_package_again_adds_nothing(env, capsys):
    _run(env)  # 省略 --slug：单租户部署并入 default

    printed = capsys.readouterr().out
    assert "没有需要导入的数据" in printed
    assert "新增 0" in printed


def test_replace_dry_run_describes_scope(env, capsys):
    _run(env, "--slug", TARGET, "--mode", "replace", "--dry-run")

    printed = capsys.readouterr().out
    assert "覆盖预览（未写入任何数据）" in printed
    assert f"记录：包内 {EXPECTED_RECORDS}" in printed


def test_missing_target_is_validation_failure(env, capsys):
    assert _exit_code(env, "--slug", "nobody") == 2
    assert "replace" in capsys.readouterr().err


def test_overwrite_with_merge_is_validation_failure(env, capsys):
    assert _exit_code(env, "--slug", TARGET, "--mode", "merge", "--overwrite") == 2
    assert "--overwrite" in capsys.readouterr().err


def test_import_failure_exits_one_and_rolls_back(env, settings, monkeypatch, capsys):
    def broken(*_args, **_kwargs):
        raise OSError("虚构磁盘故障")

    monkeypatch.setattr(merge_apply_records, "place_file", broken)

    assert _exit_code(env, "--slug", TARGET) == 1
    assert "已回滚" in capsys.readouterr().err
    assert _records(settings) == 0
