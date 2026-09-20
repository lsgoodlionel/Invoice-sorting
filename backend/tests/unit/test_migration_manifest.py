"""清单与打包工具的单元测试：路径安全、体积上限、清单解析与文件名生成。"""

import json
from datetime import datetime

import pytest

from invoice_sorting.common.errors import AppError
from invoice_sorting.migration.archive import (
    MAX_MEMBERS,
    MAX_TOTAL_BYTES,
    check_entries,
    is_safe_relative_path,
)
from invoice_sorting.migration.export import export_filename
from invoice_sorting.migration.manifest import (
    FORMAT,
    FileEntry,
    Manifest,
    build_manifest,
    parse_manifest,
    section_of,
)

DIGEST = "a" * 64
SAFE_PATHS = ("invoice.db", "文件库/2026/09/记录/发票_1.pdf", "资料包/九月/包.zip")
UNSAFE_PATHS = (
    "",
    "/etc/passwd",
    "../逃逸.pdf",
    "文件库/../../逃逸.pdf",
    "文件库/./发票.pdf",
    "C:/Windows/system32",
    "文件库\\发票.pdf",
    "~/私密文件",
    " 文件库/发票.pdf",
)


def _entry(path: str, size: int = 10) -> FileEntry:
    return FileEntry(path=path, size=size, sha256=DIGEST)


def _manifest(*entries: FileEntry) -> Manifest:
    return build_manifest("demo", "示例账套", datetime(2026, 9, 20, 8, 30), entries, {})


@pytest.mark.parametrize("path", SAFE_PATHS)
def test_safe_paths_are_accepted(path):
    assert is_safe_relative_path(path) is True


@pytest.mark.parametrize("path", UNSAFE_PATHS)
def test_unsafe_paths_are_rejected(path):
    assert is_safe_relative_path(path) is False


def test_section_of_classifies_by_directory():
    assert section_of("invoice.db") == "database"
    assert section_of("文件库/2026/发票.pdf") == "library"
    assert section_of("资料包/九月/包.zip") == "packages"


def test_manifest_summarizes_sections_and_total():
    manifest = _manifest(_entry("invoice.db", 100), _entry("文件库/a.pdf", 20))

    assert manifest.total_bytes == 120
    assert manifest.sections() == {
        "database": {"files": 1, "bytes": 100},
        "library": {"files": 1, "bytes": 20},
    }
    assert manifest.has_database is True


def test_manifest_roundtrips_through_json():
    original = _manifest(_entry("invoice.db", 7))

    restored = parse_manifest(original.to_bytes())

    assert restored.tenant_slug == "demo" and restored.tenant_name == "示例账套"
    assert restored.files == original.files
    assert json.loads(original.to_bytes())["format"] == FORMAT


def test_duplicate_paths_are_rejected():
    with pytest.raises(AppError, match="重复文件路径"):
        check_entries(_manifest(_entry("文件库/a.pdf"), _entry("文件库/a.pdf")))


def test_normal_manifest_passes_all_checks():
    manifest = _manifest(_entry("invoice.db", 100), _entry("文件库/a.pdf", 20))

    check_entries(manifest)  # 不抛异常即为通过

    assert len(manifest.files) < MAX_MEMBERS


def test_oversized_total_is_rejected():
    manifest = _manifest(_entry("invoice.db", MAX_TOTAL_BYTES + 1))

    with pytest.raises(AppError, match="体积过大"):
        check_entries(manifest)


def test_traversal_path_in_manifest_is_rejected():
    manifest = _manifest(_entry("../逃逸.pdf"))

    with pytest.raises(AppError, match="非法文件路径"):
        check_entries(manifest)


def test_broken_json_is_rejected():
    with pytest.raises(AppError, match="无法解析"):
        parse_manifest("{ 不是 json".encode())


def test_foreign_format_is_rejected():
    with pytest.raises(AppError, match="格式不符"):
        parse_manifest(json.dumps({"format": "other"}).encode())


def test_broken_file_list_is_rejected():
    payload = {"format": FORMAT, "format_version": 1, "files": [{"path": "a", "size": "大"}]}

    with pytest.raises(AppError, match="文件清单"):
        parse_manifest(json.dumps(payload).encode())


def test_export_filename_is_stable_and_unique():
    moment = datetime(2026, 9, 20, 8, 30, 5)

    assert export_filename("alpha", moment) == "账套_alpha_20260920_083005.zip"
    assert export_filename("alpha", moment, "ab12") == "账套_alpha_20260920_083005_ab12.zip"
