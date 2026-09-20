"""命令行 `invoice-sorting diagnose`（设计《日志与故障上报》5.1、5.2）。"""

from pathlib import Path

import pytest

from invoice_sorting.diagnostics import cli as diagnostics_cli
from invoice_sorting.diagnostics.cli import EXIT_FAILED, EXIT_OK, EXIT_UPLOAD_FAILED, run_diagnose
from invoice_sorting.diagnostics.constants import MSG_UPLOAD_DISABLED, REASON_CRASH, REASON_MANUAL
from invoice_sorting.main import _parse_args
from tests.conftest import make_settings
from tests.diagnostics_helpers import (
    FAKE_REPO,
    FAKE_TOKEN,
    FakeTransport,
    network_error,
    stub_commands,
)


def _run(settings, reason=REASON_MANUAL, upload=False) -> int:
    with pytest.raises(SystemExit) as exit_info:
        run_diagnose(settings, reason, upload)
    return exit_info.value.code


def test_diagnose_writes_package_and_exits_zero(tmp_path: Path, monkeypatch, capsys, clean_root):
    # Arrange
    stub_commands(monkeypatch)
    settings = make_settings(tmp_path)

    # Act
    code = _run(settings, REASON_CRASH)

    # Assert
    assert code == EXIT_OK
    assert "诊断包已生成" in capsys.readouterr().out
    assert len(list(settings.diagnostics_dir.glob("diag_*.zip"))) == 1


def test_upload_without_configuration_is_not_an_error(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    """默认不上传：加了 --upload 也只提示一句，退出码仍是 0。"""
    stub_commands(monkeypatch)
    transport = FakeTransport().install(monkeypatch)

    code = _run(make_settings(tmp_path), upload=True)

    assert code == EXIT_OK
    assert MSG_UPLOAD_DISABLED in capsys.readouterr().out
    assert transport.calls == []


def test_successful_upload_prints_repo_path(tmp_path: Path, monkeypatch, capsys, clean_root):
    stub_commands(monkeypatch)
    FakeTransport().install(monkeypatch)
    settings = make_settings(tmp_path, log_repo=FAKE_REPO, log_token=FAKE_TOKEN)

    code = _run(settings, upload=True)

    assert code == EXIT_OK
    assert "仓库内路径：invoice-sorting/logs/" in capsys.readouterr().out


def test_failed_upload_exits_with_two(tmp_path: Path, monkeypatch, capsys, clean_root):
    stub_commands(monkeypatch)
    FakeTransport(responses=[network_error()] * 5).install(monkeypatch)
    monkeypatch.setattr("invoice_sorting.diagnostics.uploader.time.sleep", lambda _s: None)
    settings = make_settings(tmp_path, log_repo=FAKE_REPO, log_token=FAKE_TOKEN)

    code = _run(settings, upload=True)

    assert code == EXIT_UPLOAD_FAILED
    assert "无法连接日志仓库" in capsys.readouterr().out


def test_unknown_reason_exits_with_one(tmp_path: Path, capsys, clean_root) -> None:
    code = _run(make_settings(tmp_path), reason="随便写")

    assert code == EXIT_FAILED
    assert "reason" in capsys.readouterr().err


def test_collect_failure_exits_with_one(tmp_path: Path, monkeypatch, capsys, clean_root):
    stub_commands(monkeypatch)
    monkeypatch.setattr(
        "invoice_sorting.diagnostics.service.collect_package",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("磁盘满")),
    )

    code = _run(make_settings(tmp_path))

    assert code == EXIT_FAILED
    assert "生成诊断包失败" in capsys.readouterr().err


def test_argv_parsing_matches_the_design() -> None:
    args = _parse_args(["diagnose", "--upload", "--reason=crash"])

    assert args.command == "diagnose"
    assert args.upload is True
    assert args.reason == REASON_CRASH


def test_argv_defaults_to_manual_without_upload() -> None:
    args = _parse_args(["diagnose"])

    assert args.upload is False
    assert args.reason == REASON_MANUAL


def test_exit_codes_are_documented() -> None:
    """部署脚本按退出码判断，值不能随手改。"""
    assert (EXIT_OK, EXIT_FAILED, EXIT_UPLOAD_FAILED) == (0, 1, 2)
    assert diagnostics_cli.__doc__ is not None
