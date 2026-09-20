"""搬迁往返一致性（设计 7）：导出 → 导入为新账套，两边记录、金额与附件字节完全一致。"""

import hashlib
import json
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import select

from invoice_sorting.common.errors import AppError
from invoice_sorting.db.models import Expense
from invoice_sorting.migration.export import export_tenant
from invoice_sorting.migration.manifest import FORMAT, MANIFEST_NAME
from invoice_sorting.migration.restore import import_tenant
from tests.migration_helpers import (
    PACKAGE_FILENAME,
    SAMPLE_EXPENSES,
    seed_tenant_data,
    snapshot_of,
)

SOURCE_SLUG = "default"
TARGET_SLUG = "copy1"
TENANT_NAME = "虚构默认账套"


@pytest.fixture
def seeded(app, settings, session, tmp_path):
    """一个含记录、附件文件、批次、导出记录与分类记忆的虚构账套。"""
    seed_tenant_data(session, settings, tmp_path / "来源")
    return app


def export_to(app, out: Path, include_packages: bool = True):
    context = app.state.tenants.get(SOURCE_SLUG)
    return export_tenant(context, out, tenant_name=TENANT_NAME, include_packages=include_packages)


def import_as(app, archive: Path, slug: str, overwrite: bool = False):
    return import_tenant(
        app.state.tenants,
        app.state.control_session_factory,
        archive,
        slug,
        overwrite=overwrite,
    )


def read_manifest(archive: Path) -> dict:
    with zipfile.ZipFile(archive) as package:
        return json.loads(package.read(MANIFEST_NAME).decode("utf-8"))


def test_roundtrip_keeps_records_amounts_and_files(seeded, tmp_path):
    out = tmp_path / "搬迁包.zip"
    exported = export_to(seeded, out)

    imported = import_as(seeded, out, TARGET_SLUG)

    assert imported.file_count == exported.file_count
    assert snapshot_of(seeded, TARGET_SLUG) == snapshot_of(seeded, SOURCE_SLUG)


def test_imported_tenant_is_registered_and_usable(seeded, tmp_path):
    out = tmp_path / "搬迁包.zip"
    export_to(seeded, out)

    imported = import_as(seeded, out, TARGET_SLUG)
    context = seeded.state.tenants.get(TARGET_SLUG)
    with context.session_factory() as db:
        merchants = sorted(row.merchant for row in db.scalars(select(Expense)))

    assert imported.tenant_id > 0
    assert merchants == sorted(name for name, _, _ in SAMPLE_EXPENSES)
    assert context.settings.data_dir == seeded.state.settings.data_dir / "tenants" / TARGET_SLUG


def test_manifest_records_versions_sections_and_checksums(seeded, tmp_path):
    out = tmp_path / "搬迁包.zip"
    exported = export_to(seeded, out)

    manifest = read_manifest(out)

    assert manifest["format"] == FORMAT and manifest["format_version"] == 1
    assert manifest["tenant"] == {"slug": SOURCE_SLUG, "name": TENANT_NAME}
    assert set(manifest["schema_versions"]) == {
        "keywords_version",
        "rules_version",
        "classification_memory_version",
    }
    assert set(manifest["sections"]) == {"database", "library", "packages"}
    assert manifest["sections"]["library"]["files"] == len(SAMPLE_EXPENSES)
    assert manifest["total_bytes"] == exported.total_bytes
    assert all(len(row["sha256"]) == 64 for row in manifest["files"])


def test_manifest_checksums_match_archive_content(seeded, tmp_path):
    out = tmp_path / "搬迁包.zip"
    export_to(seeded, out)

    manifest = read_manifest(out)
    with zipfile.ZipFile(out) as package:
        digests = {
            row["path"]: hashlib.sha256(package.read(f"data/{row['path']}")).hexdigest()
            for row in manifest["files"]
        }

    assert digests == {row["path"]: row["sha256"] for row in manifest["files"]}


def test_export_does_not_disturb_source_wal(seeded, tmp_path, settings):
    context = seeded.state.tenants.get(SOURCE_SLUG)
    export_to(seeded, tmp_path / "搬迁包.zip")

    with context.engine.connect() as conn:
        mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
    with context.session_factory() as db:
        db.add(Expense(spent_on=SAMPLE_EXPENSES[0][2], amount_cents=100, merchant="导出后新增"))
        db.commit()
        remaining = len(list(db.scalars(select(Expense))))

    assert mode == "wal"
    assert remaining == len(SAMPLE_EXPENSES) + 1
    assert settings.db_path.exists()


def test_no_packages_option_skips_package_files(seeded, tmp_path):
    out = tmp_path / "无资料包.zip"

    export_to(seeded, out, include_packages=False)
    import_as(seeded, out, TARGET_SLUG)

    manifest = read_manifest(out)
    target = seeded.state.tenants.get(TARGET_SLUG).settings
    assert "packages" not in manifest["sections"]
    assert not any(target.packages_dir.rglob(PACKAGE_FILENAME))


def test_existing_slug_is_rejected_without_overwrite(seeded, tmp_path):
    out = tmp_path / "搬迁包.zip"
    export_to(seeded, out)

    with pytest.raises(AppError) as excinfo:
        import_as(seeded, out, SOURCE_SLUG)

    assert excinfo.value.status_code == 409
    assert "已存在" in excinfo.value.message


def test_overwrite_backs_up_existing_data_first(seeded, tmp_path):
    out = tmp_path / "搬迁包.zip"
    export_to(seeded, out)
    import_as(seeded, out, TARGET_SLUG)
    target = seeded.state.tenants.get(TARGET_SLUG).settings
    (target.library_dir / "多余文件.txt").write_text("应被覆盖清除", encoding="utf-8")

    imported = import_as(seeded, out, TARGET_SLUG, overwrite=True)

    assert imported.backup_path is not None
    assert imported.backup_path.is_file()
    assert imported.backup_path.parent == target.backup_dir
    assert not (target.library_dir / "多余文件.txt").exists()
    assert snapshot_of(seeded, TARGET_SLUG) == snapshot_of(seeded, SOURCE_SLUG)
