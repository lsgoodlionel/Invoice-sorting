"""命令行搬迁：export-tenant / import-tenant 的正常路径、冲突拒绝与覆盖备份。"""

import sqlite3
import zipfile
from contextlib import closing
from pathlib import Path

import pytest

from invoice_sorting import main
from invoice_sorting.migration.jobs import exports_dir
from tests.migration_helpers import SAMPLE_EXPENSES, seed_tenant_data

TARGET_SLUG = "cli-copy"


@pytest.fixture
def seeded_env(app, settings, session, tmp_path, monkeypatch):
    """把虚构账套准备好，并让命令行与测试夹具指向同一个数据目录。"""
    seed_tenant_data(session, settings, tmp_path / "来源")
    monkeypatch.setenv("INVOICE_SORTING_DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("INVOICE_SORTING_WATCH_INBOX", "false")
    return settings


def _expense_count(db_path: Path) -> int:
    with closing(sqlite3.connect(db_path)) as conn:
        return conn.execute("select count(*) from expense").fetchone()[0]


def _export(out: Path, *extra: str) -> None:
    main.run(["export-tenant", "--out", str(out), *extra])


def test_export_defaults_to_single_tenant(seeded_env, tmp_path, capsys):
    out = tmp_path / "搬迁包.zip"

    _export(out)

    printed = capsys.readouterr().out
    assert out.is_file()
    assert "已导出账套 default" in printed
    assert f"文件 {len(SAMPLE_EXPENSES) + 2} 个" in printed  # 数据库 + 附件 + 资料包


def test_export_without_out_writes_to_backup_dir(seeded_env, capsys):
    main.run(["export-tenant"])

    packages = list(exports_dir(seeded_env).glob("*.zip"))
    assert len(packages) == 1
    assert packages[0].name in capsys.readouterr().out


def test_export_skips_packages_on_request(seeded_env, tmp_path):
    out = tmp_path / "无资料包.zip"

    _export(out, "--no-packages")

    with zipfile.ZipFile(out) as package:
        assert not any(name.startswith("data/资料包/") for name in package.namelist())


def test_export_unknown_tenant_exits_nonzero(seeded_env, tmp_path, capsys):
    with pytest.raises(SystemExit) as exited:
        _export(tmp_path / "x.zip", "--slug", "nobody")

    assert exited.value.code == 1
    assert "账套不存在：nobody" in capsys.readouterr().err


def test_export_invalid_slug_exits_nonzero(seeded_env, tmp_path, capsys):
    with pytest.raises(SystemExit) as exited:
        _export(tmp_path / "x.zip", "--slug", "坏 slug")

    assert exited.value.code == 1
    assert "账套标识" in capsys.readouterr().err


def _replace(out: Path, *extra: str) -> None:
    main.run(
        ["import-tenant", "--in", str(out), "--slug", TARGET_SLUG, "--mode", "replace", *extra]
    )


def test_import_creates_new_tenant(seeded_env, tmp_path, capsys):
    out = tmp_path / "搬迁包.zip"
    _export(out)
    capsys.readouterr()

    _replace(out)

    target_db = seeded_env.data_dir / "tenants" / TARGET_SLUG / "invoice.db"
    assert f"覆盖导入完成：账套 {TARGET_SLUG}" in capsys.readouterr().out
    assert _expense_count(target_db) == len(SAMPLE_EXPENSES)


def test_import_refuses_existing_tenant(seeded_env, tmp_path, capsys):
    out = tmp_path / "搬迁包.zip"
    _export(out)
    _replace(out)
    capsys.readouterr()

    with pytest.raises(SystemExit) as exited:
        _replace(out)

    assert exited.value.code == 2  # 校验失败：未写入任何数据
    assert "已存在" in capsys.readouterr().err


def test_import_overwrite_backs_up_first(seeded_env, tmp_path, capsys):
    out = tmp_path / "搬迁包.zip"
    _export(out)
    _replace(out)
    capsys.readouterr()

    main.run(["import-tenant", "--in", str(out), "--slug", TARGET_SLUG, "--overwrite"])

    printed = capsys.readouterr().out
    target_dir = seeded_env.data_dir / "tenants" / TARGET_SLUG
    backups = list((target_dir / "备份").glob("覆盖前备份_*.zip"))
    assert "覆盖前已备份现有数据" in printed
    assert len(backups) == 1
    assert _expense_count(target_dir / "invoice.db") == len(SAMPLE_EXPENSES)


def test_import_rejects_broken_archive(seeded_env, tmp_path, capsys):
    fake = tmp_path / "坏包.zip"
    fake.write_text("不是压缩包", encoding="utf-8")

    with pytest.raises(SystemExit) as exited:
        main.run(["import-tenant", "--in", str(fake), "--slug", TARGET_SLUG])

    assert exited.value.code == 2
    assert "zip" in capsys.readouterr().err
