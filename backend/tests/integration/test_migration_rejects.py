"""搬迁包的安全与校验：损坏、篡改、目录穿越、版本过新、非法 slug 一律拒绝并说明原因。"""

import json
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest

from invoice_sorting.common.errors import AppError
from invoice_sorting.migration.manifest import MANIFEST_NAME
from tests.integration.test_migration_roundtrip import (
    TARGET_SLUG,
    export_to,
    import_as,
    seeded,  # noqa: F401 - pytest 夹具需要在本模块可见
)

LIBRARY_PREFIX = "data/文件库/"
Transform = Callable[[str, bytes], tuple[str, bytes]]


def _repack(source: Path, target: Path, transform: Transform) -> Path:
    """按 transform(成员名, 内容) 重写包内成员，用于构造各种坏包。"""
    with zipfile.ZipFile(source) as original:
        members = [(info.filename, original.read(info.filename)) for info in original.infolist()]
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as rebuilt:
        for name, data in members:
            new_name, new_data = transform(name, data)
            rebuilt.writestr(new_name, new_data)
    return target


def _patch_manifest(change: Callable[[dict], dict]) -> Transform:
    def transform(name: str, data: bytes) -> tuple[str, bytes]:
        if name != MANIFEST_NAME:
            return name, data
        payload = change(json.loads(data.decode("utf-8")))
        return name, json.dumps(payload, ensure_ascii=False).encode("utf-8")

    return transform


def _first_library_member(archive: Path) -> str:
    with zipfile.ZipFile(archive) as package:
        return next(
            info.filename for info in package.infolist() if info.filename.startswith(LIBRARY_PREFIX)
        )


def _exported(app, tmp_path: Path) -> Path:
    out = tmp_path / "搬迁包.zip"
    export_to(app, out)
    return out


def test_tampered_file_content_is_rejected(seeded, tmp_path):  # noqa: F811
    """内容被换掉但长度与 CRC 都自洽的包：靠清单里的 SHA-256 识破。"""
    source = _exported(seeded, tmp_path)
    member = _first_library_member(source)

    def swap(name: str, data: bytes) -> tuple[str, bytes]:
        return (name, b"X" * len(data)) if name == member else (name, data)

    broken = _repack(source, tmp_path / "被篡改.zip", swap)

    with pytest.raises(AppError) as excinfo:
        import_as(seeded, broken, TARGET_SLUG)

    assert "校验和不符" in excinfo.value.message


def test_single_flipped_byte_is_rejected(seeded, tmp_path):  # noqa: F811
    """原包只改一个字节（压缩流损坏）也必须被拒绝，且不留下半个账套。"""
    source = _exported(seeded, tmp_path)
    broken = tmp_path / "损坏.zip"
    broken.write_bytes(_flip_byte(source, _first_library_member(source)))

    with pytest.raises(AppError):
        import_as(seeded, broken, TARGET_SLUG)

    assert not (seeded.state.settings.data_dir / "tenants" / TARGET_SLUG / "invoice.db").exists()


def _flip_byte(archive: Path, member: str) -> bytes:
    """翻转某成员压缩数据中的一个字节（跳过本地文件头）。"""
    raw = bytearray(archive.read_bytes())
    with zipfile.ZipFile(archive) as package:
        offset = package.getinfo(member).header_offset
    name_len = int.from_bytes(raw[offset + 26 : offset + 28], "little")
    extra_len = int.from_bytes(raw[offset + 28 : offset + 30], "little")
    position = offset + 30 + name_len + extra_len + 3
    raw[position] ^= 0xFF
    return bytes(raw)


def test_directory_traversal_path_is_rejected(seeded, tmp_path):  # noqa: F811
    """zip slip：清单里出现 `..` 时直接拒绝，绝不写到租户目录之外。"""
    source = _exported(seeded, tmp_path)
    member = _first_library_member(source)
    evil_path = "../../被穿越.pdf"

    def transform(name: str, data: bytes) -> tuple[str, bytes]:
        if name == MANIFEST_NAME:
            payload = json.loads(data.decode("utf-8"))
            rows = [
                {**row, "path": evil_path} if f"data/{row['path']}" == member else row
                for row in payload["files"]
            ]
            return name, json.dumps({**payload, "files": rows}, ensure_ascii=False).encode()
        target = f"data/{evil_path}" if name == member else name
        return target, data

    broken = _repack(source, tmp_path / "穿越.zip", transform)

    with pytest.raises(AppError) as excinfo:
        import_as(seeded, broken, TARGET_SLUG)

    assert "非法文件路径" in excinfo.value.message
    assert not (tmp_path / "被穿越.pdf").exists()


def test_absolute_path_is_rejected(seeded, tmp_path):  # noqa: F811
    source = _exported(seeded, tmp_path)
    change = _patch_manifest(
        lambda payload: {
            **payload,
            "files": [{**row, "path": "/etc/passwd"} for row in payload["files"][:1]]
            + payload["files"][1:],
        }
    )

    broken = _repack(source, tmp_path / "绝对路径.zip", change)

    with pytest.raises(AppError) as excinfo:
        import_as(seeded, broken, TARGET_SLUG)

    assert "非法文件路径" in excinfo.value.message


def test_oversized_declaration_is_rejected(seeded, tmp_path):  # noqa: F811
    """zip 炸弹防护：清单声明的解包体积超过上限时提前拒绝。"""
    source = _exported(seeded, tmp_path)
    huge = 60 * 1024 * 1024 * 1024
    change = _patch_manifest(
        lambda payload: {
            **payload,
            "files": [{**row, "size": huge} for row in payload["files"]],
        }
    )

    broken = _repack(source, tmp_path / "体积异常.zip", change)

    with pytest.raises(AppError) as excinfo:
        import_as(seeded, broken, TARGET_SLUG)

    assert "体积过大" in excinfo.value.message


def test_newer_format_version_is_rejected(seeded, tmp_path):  # noqa: F811
    source = _exported(seeded, tmp_path)
    change = _patch_manifest(lambda payload: {**payload, "format_version": 99})

    broken = _repack(source, tmp_path / "新版本.zip", change)

    with pytest.raises(AppError) as excinfo:
        import_as(seeded, broken, TARGET_SLUG)

    assert "版本过新" in excinfo.value.message


def test_newer_schema_version_is_rejected(seeded, tmp_path):  # noqa: F811
    source = _exported(seeded, tmp_path)
    change = _patch_manifest(
        lambda payload: {
            **payload,
            "schema_versions": {**payload["schema_versions"], "rules_version": "999"},
        }
    )

    broken = _repack(source, tmp_path / "新规则.zip", change)

    with pytest.raises(AppError) as excinfo:
        import_as(seeded, broken, TARGET_SLUG)

    assert "rules_version" in excinfo.value.message and "升级程序" in excinfo.value.message


def test_archive_without_manifest_is_rejected(seeded, tmp_path):  # noqa: F811
    source = _exported(seeded, tmp_path)
    stripped = tmp_path / "无清单.zip"
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(stripped, "w") as rebuilt:
        for info in original.infolist():
            if info.filename != MANIFEST_NAME:
                rebuilt.writestr(info.filename, original.read(info.filename))

    with pytest.raises(AppError) as excinfo:
        import_as(seeded, stripped, TARGET_SLUG)

    assert "manifest.json" in excinfo.value.message


def test_non_zip_file_is_rejected(seeded, tmp_path):  # noqa: F811
    fake = tmp_path / "不是压缩包.zip"
    fake.write_text("这只是一个文本文件", encoding="utf-8")

    with pytest.raises(AppError) as excinfo:
        import_as(seeded, fake, TARGET_SLUG)

    assert "zip" in excinfo.value.message


def test_missing_archive_is_rejected(seeded, tmp_path):  # noqa: F811
    with pytest.raises(AppError) as excinfo:
        import_as(seeded, tmp_path / "不存在.zip", TARGET_SLUG)

    assert excinfo.value.status_code == 404


def test_invalid_slug_is_rejected(seeded, tmp_path):  # noqa: F811
    source = _exported(seeded, tmp_path)

    with pytest.raises(AppError) as excinfo:
        import_as(seeded, source, "../坏账套")

    assert "账套标识" in excinfo.value.message
