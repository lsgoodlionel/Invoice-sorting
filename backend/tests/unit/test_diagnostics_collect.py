"""诊断包内容、体积截断与保留数量（设计《日志与故障上报》3）。"""

import json
from datetime import timedelta
from pathlib import Path

import pytest

from invoice_sorting.diagnostics.collect import collect_package, prune_packages
from invoice_sorting.diagnostics.constants import (
    ENV_SET,
    KEEP_PACKAGES,
    MAX_PACKAGE_BYTES,
    MEMBER_APP_LOG,
    MEMBER_ENV,
    MEMBER_HEALTH,
    MEMBER_JOURNAL,
    MEMBER_NGINX,
    MEMBER_SERVICE,
    MEMBER_SUMMARY,
    REASON_CRASH,
    REASON_MANUAL,
)
from invoice_sorting.diagnostics.fingerprint import Fault, make_fingerprint
from tests.conftest import make_settings
from tests.diagnostics_helpers import FIXED_TIME, package_members, stub_commands


@pytest.fixture
def diag_settings(tmp_path: Path, monkeypatch):
    stub_commands(monkeypatch)
    settings = make_settings(tmp_path)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    return settings


def _write_log(settings, text: str) -> None:
    settings.log_file.write_text(text, encoding="utf-8")


def test_package_contains_every_designed_member(diag_settings) -> None:
    # Arrange
    _write_log(diag_settings, "启动完成\n")

    # Act
    result = collect_package(diag_settings, REASON_MANUAL, FIXED_TIME)

    # Assert
    assert set(package_members(result.path)) == {
        MEMBER_SUMMARY,
        MEMBER_APP_LOG,
        MEMBER_JOURNAL,
        MEMBER_SERVICE,
        MEMBER_NGINX,
        MEMBER_ENV,
        MEMBER_HEALTH,
    }


def test_package_name_carries_time_and_fingerprint(diag_settings) -> None:
    fault = Fault(make_fingerprint("ValueError", "main.py:1"), "ValueError", "main.py:1")

    result = collect_package(diag_settings, REASON_CRASH, FIXED_TIME, fault=fault)

    assert result.path.name.startswith("diag_")
    assert "20260920-123000" in result.path.name
    assert result.path.name.endswith(f"{fault.short}.zip")
    assert result.path.parent == diag_settings.diagnostics_dir


def test_package_lands_in_diagnostics_dir_without_fingerprint(diag_settings) -> None:
    result = collect_package(diag_settings, REASON_MANUAL, FIXED_TIME)

    assert result.fingerprint == ""
    assert result.path.exists()


def test_summary_records_reason_and_scale_without_record_details(diag_settings) -> None:
    result = collect_package(diag_settings, REASON_CRASH, FIXED_TIME)

    summary = json.loads(package_members(result.path)[MEMBER_SUMMARY])
    assert summary["reason"] == REASON_CRASH
    assert summary["deployment_mode"] == "single"
    assert "records" in summary["scale"]
    assert summary["upload_configured"] is False


def test_env_file_lists_names_only_never_values(diag_settings, monkeypatch) -> None:
    # Arrange：环境变量里放一个明显的假令牌，它绝不能出现在包里
    monkeypatch.setenv("INVOICE_SORTING_LOG_TOKEN", "fake-token-must-not-leak")

    # Act
    result = collect_package(diag_settings, REASON_MANUAL, FIXED_TIME)

    # Assert
    members = package_members(result.path)
    assert f"INVOICE_SORTING_LOG_TOKEN  {ENV_SET}" in members[MEMBER_ENV]
    assert all("fake-token-must-not-leak" not in content for content in members.values())


def test_app_log_is_redacted_inside_package(diag_settings) -> None:
    _write_log(diag_settings, "导入失败 li@example-corp.cn 手机 13800001111\n")

    result = collect_package(diag_settings, REASON_MANUAL, FIXED_TIME)

    log = package_members(result.path)[MEMBER_APP_LOG]
    assert "li@example-corp.cn" not in log
    assert "13800001111" not in log
    assert "<邮箱>" in log


def test_package_passes_residue_self_check(diag_settings) -> None:
    _write_log(diag_settings, "用户 li@example.cn 卡号 6222021234567890123\n")

    result = collect_package(diag_settings, REASON_MANUAL, FIXED_TIME)

    assert result.residue == ()
    assert result.is_safe_to_upload


def test_app_log_tail_is_limited(diag_settings) -> None:
    _write_log(diag_settings, "".join(f"第{index}行\n" for index in range(5000)))

    result = collect_package(diag_settings, REASON_MANUAL, FIXED_TIME)

    log = package_members(result.path)[MEMBER_APP_LOG]
    assert "第4999行" in log
    assert "第100行" not in log


def test_oversized_log_is_truncated_to_the_budget(diag_settings, monkeypatch) -> None:
    # Arrange：把上限调小，用可控的数据量验证截断逻辑
    monkeypatch.setattr("invoice_sorting.diagnostics.collect.MAX_PACKAGE_BYTES", 4096)
    _write_log(diag_settings, "".join(f"第{index}行 服务异常\n" for index in range(5000)))

    # Act
    result = collect_package(diag_settings, REASON_MANUAL, FIXED_TIME)

    # Assert
    members = package_members(result.path)
    assert result.is_truncated
    assert "已截断" in members[MEMBER_APP_LOG]
    assert sum(len(content.encode()) for content in members.values()) <= 4096


def test_huge_raw_log_still_produces_package_within_limit(diag_settings) -> None:
    """真实故障现场的日志可能非常大：先按尾部读取再截断，包体不会失控。"""
    _write_log(diag_settings, "服务异常 无法写入磁盘\n" * 400_000)

    result = collect_package(diag_settings, REASON_MANUAL, FIXED_TIME)

    assert result.size <= MAX_PACKAGE_BYTES


def test_health_member_is_written_when_provided(diag_settings) -> None:
    result = collect_package(
        diag_settings, REASON_MANUAL, FIXED_TIME, health={"health": {"status": "up"}}
    )

    assert json.loads(package_members(result.path)[MEMBER_HEALTH])["health"]["status"] == "up"


def test_only_latest_packages_are_kept(diag_settings) -> None:
    for index in range(KEEP_PACKAGES + 3):
        collect_package(diag_settings, REASON_MANUAL, FIXED_TIME + timedelta(seconds=index))

    remaining = list(diag_settings.diagnostics_dir.glob("diag_*.zip"))
    assert len(remaining) == KEEP_PACKAGES


def test_prune_ignores_missing_directory(tmp_path: Path) -> None:
    prune_packages(tmp_path / "不存在")  # 不抛异常即可
