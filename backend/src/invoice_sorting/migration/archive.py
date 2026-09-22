"""搬迁包的 zip 读写：路径安全校验、流式写入与带校验和的流式解包。

安全约定（导入端把搬迁包当作不可信输入）：
- 成员路径必须是相对路径，不含 `..`、盘符与反斜杠，杜绝 zip slip；
- 只解清单里列出的成员，多出来的成员一律忽略；
- 解包按清单声明的大小逐块读取，读满即停，避免 zip 炸弹撑爆磁盘。
"""

import hashlib
import zipfile
import zlib
from collections.abc import Iterator
from pathlib import Path

from invoice_sorting.common.errors import AppError
from invoice_sorting.migration.manifest import FileEntry, Manifest

CHUNK_BYTES = 1024 * 1024
MAX_MEMBERS = 200_000
MAX_TOTAL_BYTES = 50 * 1024 * 1024 * 1024  # 单个搬迁包最多 50 GiB（解包后）

MSG_UNSAFE_PATH = "搬迁包内含非法文件路径：{path}"
MSG_TOO_MANY_FILES = "搬迁包内文件过多（{found} 个），超出上限 {limit}"
MSG_TOO_LARGE = "搬迁包解包后体积过大（{found} 字节），超出上限 {limit}"
MSG_MEMBER_MISSING = "搬迁包缺少文件：{path}"
MSG_SIZE_MISMATCH = "搬迁包文件大小与清单不符：{path}"
MSG_CHECKSUM_MISMATCH = "搬迁包文件校验和不符（可能已损坏或被篡改）：{path}"
MSG_BAD_ZIP = "搬迁包不是有效的 zip 文件，或已损坏"
MSG_DUPLICATE_PATH = "搬迁包内含重复文件路径：{path}"


def is_safe_relative_path(path: str) -> bool:
    """只接受干净的相对 POSIX 路径；绝对路径、`..`、盘符与反斜杠全部拒绝。"""
    if not path or "\x00" in path or path != path.strip():
        return False
    if path.startswith(("/", "\\", "~")) or ":" in path or "\\" in path:
        return False
    return all(part not in ("", ".", "..") for part in path.split("/"))


def check_entries(manifest: Manifest) -> None:
    """导入前对整份清单做一次性体检：路径、重复、数量与总体积。"""
    if len(manifest.files) > MAX_MEMBERS:
        raise AppError(MSG_TOO_MANY_FILES.format(found=len(manifest.files), limit=MAX_MEMBERS))
    if manifest.total_bytes > MAX_TOTAL_BYTES:
        raise AppError(MSG_TOO_LARGE.format(found=manifest.total_bytes, limit=MAX_TOTAL_BYTES))
    seen: set[str] = set()
    for entry in manifest.files:
        if not is_safe_relative_path(entry.path):
            raise AppError(MSG_UNSAFE_PATH.format(path=entry.path))
        if entry.path in seen:
            raise AppError(MSG_DUPLICATE_PATH.format(path=entry.path))
        seen.add(entry.path)


def open_archive(path: Path) -> zipfile.ZipFile:
    """打开搬迁包；不是 zip 或已损坏时给出中文原因。"""
    try:
        return zipfile.ZipFile(path, "r")
    except (zipfile.BadZipFile, OSError) as error:
        raise AppError(MSG_BAD_ZIP) from error


def add_file(archive: zipfile.ZipFile, source: Path, member: str) -> tuple[int, str]:
    """流式写入一个文件，返回 (字节数, sha256)；不把整个文件读进内存。"""
    digest = hashlib.sha256()
    size = 0
    with source.open("rb") as handle:
        with archive.open(member, "w", force_zip64=True) as target:
            while chunk := handle.read(CHUNK_BYTES):
                digest.update(chunk)
                size += len(chunk)
                target.write(chunk)
    return size, digest.hexdigest()


def add_bytes(archive: zipfile.ZipFile, data: bytes, member: str) -> tuple[int, str]:
    """写入一段内存中的小文件（如账号清单），返回 (字节数, sha256)。"""
    archive.writestr(member, data)
    return len(data), hashlib.sha256(data).hexdigest()


def read_member(archive: zipfile.ZipFile, member: str, limit: int) -> bytes:
    """读取一个小成员（清单）；超过 limit 视为损坏。"""
    try:
        info = archive.getinfo(member)
    except KeyError as error:
        raise AppError(MSG_MEMBER_MISSING.format(path=member)) from error
    if info.file_size > limit:
        raise AppError(MSG_SIZE_MISMATCH.format(path=member))
    try:
        with archive.open(info) as handle:
            return handle.read(limit + 1)[:limit]
    except (zipfile.BadZipFile, zlib.error, EOFError) as error:
        raise AppError(MSG_BAD_ZIP) from error


def read_verified(archive: zipfile.ZipFile, entry: FileEntry, limit: int) -> bytes:
    """读取清单里的一个小文件到内存，并核对大小与校验和（不落盘，适合含敏感内容的小文件）。"""
    if entry.size > limit:
        raise AppError(MSG_SIZE_MISMATCH.format(path=entry.path))
    data = read_member(archive, entry.member, limit)
    if len(data) != entry.size:
        raise AppError(MSG_SIZE_MISMATCH.format(path=entry.path))
    if hashlib.sha256(data).hexdigest() != entry.sha256:
        raise AppError(MSG_CHECKSUM_MISMATCH.format(path=entry.path))
    return data


def extract_entry(archive: zipfile.ZipFile, entry: FileEntry, destination: Path) -> None:
    """流式解出一个文件并核对大小与校验和；读满声明大小即停止。"""
    try:
        info = archive.getinfo(entry.member)
    except KeyError as error:
        raise AppError(MSG_MEMBER_MISSING.format(path=entry.path)) from error
    if info.file_size != entry.size:
        raise AppError(MSG_SIZE_MISMATCH.format(path=entry.path))
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest, written = _copy_out(archive, info, destination, entry.size)
    if written != entry.size:
        raise AppError(MSG_SIZE_MISMATCH.format(path=entry.path))
    if digest != entry.sha256:
        raise AppError(MSG_CHECKSUM_MISMATCH.format(path=entry.path))


def _copy_out(
    archive: zipfile.ZipFile, info: zipfile.ZipInfo, destination: Path, limit: int
) -> tuple[str, int]:
    """逐块解出并同时算校验和；压缩流损坏（CRC、zlib）一律当作包已损坏。"""
    digest = hashlib.sha256()
    written = 0
    try:
        with archive.open(info) as source, destination.open("wb") as target:
            while chunk := source.read(CHUNK_BYTES):
                written += len(chunk)
                if written > limit:
                    raise AppError(MSG_SIZE_MISMATCH.format(path=info.filename))
                digest.update(chunk)
                target.write(chunk)
    except (zipfile.BadZipFile, zlib.error, EOFError) as error:
        raise AppError(MSG_CHECKSUM_MISMATCH.format(path=info.filename)) from error
    return digest.hexdigest(), written


def walk_files(root: Path) -> Iterator[Path]:
    """按字典序遍历目录下的普通文件；软链接不跟随（避免把目录外的文件打包进去）。"""
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        yield path
