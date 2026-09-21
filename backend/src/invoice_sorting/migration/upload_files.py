"""分片上传的磁盘操作：流式写片、按序合并并计算整包 SHA-256、清理过期会话。

全部按块读写，任何时候内存里最多只有一块数据，2 GB 的包也不会整包读进内存。
"""

import hashlib
import logging
import os
import shutil
import uuid
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from invoice_sorting.common.errors import AppError
from invoice_sorting.config import TENANTS_DIRNAME, Settings
from invoice_sorting.migration.upload_store import (
    SESSION_TTL,
    STAGING_DIRNAME,
    STATUS_FAILED,
    STATUS_RUNNING,
    UPLOAD_ID_PATTERN,
    load_session,
    write_session,
)

logger = logging.getLogger(__name__)

CHUNK_BYTES = 1024 * 1024
TEMP_SUFFIX = ".tmp"

MSG_PART_SIZE_MISMATCH = "分片大小与约定不符：第 {index} 片应为 {expected} 字节，实际 {found} 字节"
MSG_PART_TOO_LARGE = "分片大小与约定不符：第 {index} 片超过 {expected} 字节"
MSG_PACKAGE_SIZE_MISMATCH = "合并后的账本包大小与登记不符，请重新上传"
MSG_INTERRUPTED = "服务重启导致导入中断，请重新上传后再试"


def part_file(parts_dir: Path, index: int) -> Path:
    return parts_dir / str(index)


def received_parts(parts_dir: Path, part_count: int) -> tuple[int, ...]:
    """磁盘上已完整收到的分片号（写入中的临时文件不算）。"""
    if not parts_dir.is_dir():
        return ()
    found = {int(path.name) for path in parts_dir.iterdir() if path.name.isdigit()}
    return tuple(sorted(index for index in found if index < part_count))


async def write_part(
    chunks: AsyncIterator[bytes], parts_dir: Path, index: int, expected: int
) -> int:
    """流式写入一片：先写临时文件，大小核对通过后原子改名；同一片重传直接覆盖旧片。"""
    parts_dir.mkdir(parents=True, exist_ok=True)
    temp = parts_dir / f"{index}.{uuid.uuid4().hex}{TEMP_SUFFIX}"
    written = 0
    try:
        with temp.open("wb") as target:
            async for chunk in chunks:
                written += len(chunk)
                if written > expected:
                    raise AppError(MSG_PART_TOO_LARGE.format(index=index, expected=expected))
                target.write(chunk)
        if written != expected:
            message = MSG_PART_SIZE_MISMATCH.format(index=index, expected=expected, found=written)
            raise AppError(message)
        os.replace(temp, part_file(parts_dir, index))
    finally:
        temp.unlink(missing_ok=True)
    return written


def assemble(parts_dir: Path, part_count: int, target: Path, total_size: int) -> str:
    """按片号顺序拼接成整包并同时计算 SHA-256；大小不符时删除半成品。"""
    temp = target.with_name(target.name + TEMP_SUFFIX)
    digest = hashlib.sha256()
    size = 0
    try:
        with temp.open("wb") as output:
            for index in range(part_count):
                size += _append(part_file(parts_dir, index), output, digest)
        if size != total_size:
            raise AppError(MSG_PACKAGE_SIZE_MISMATCH)
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    return digest.hexdigest()


def _append(source: Path, output, digest) -> int:  # noqa: ANN001 - 二进制文件句柄与摘要对象
    size = 0
    with source.open("rb") as handle:
        while chunk := handle.read(CHUNK_BYTES):
            digest.update(chunk)
            output.write(chunk)
            size += len(chunk)
    return size


def sweep_root(root: Path, moment: datetime, is_startup: bool = False) -> int:
    """清理一个暂存区里过期或损坏的会话，返回清理个数。

    启动时进行中的导入不可能还在跑（后台线程随进程结束），标记为失败以免界面一直转圈。
    """
    if not root.is_dir():
        return 0
    removed = 0
    for directory in root.iterdir():
        if directory.is_dir() and _sweep_one(directory, moment, is_startup):
            removed += 1
    return removed


def _sweep_one(directory: Path, moment: datetime, is_startup: bool) -> bool:
    """只处理会话目录（名字是会话号）；其他目录（如命令行导入的解包区）一概不碰。"""
    if not UPLOAD_ID_PATTERN.match(directory.name):
        return False
    session = load_session(directory)
    if session is None:
        return _remove_if_old(directory, moment)  # 元数据损坏：按目录时间判断，避免误删刚建的
    if is_startup and session.status == STATUS_RUNNING:
        session = write_session(
            directory, replace(session, status=STATUS_FAILED, error=MSG_INTERRUPTED)
        )
    if session.status == STATUS_RUNNING or not session.is_expired(moment):
        return False
    return _remove(directory)


def _remove_if_old(directory: Path, moment: datetime) -> bool:
    modified = datetime.fromtimestamp(directory.stat().st_mtime, tz=moment.tzinfo)
    return _remove(directory) if moment - modified >= SESSION_TTL else False


def _remove(directory: Path) -> bool:
    shutil.rmtree(directory, ignore_errors=True)
    logger.info("已清理过期的导入暂存：%s", directory.name)
    return True


def staging_roots(base: Settings) -> tuple[Path, ...]:
    """部署内所有可能的导入暂存区：单租户数据目录与各账套目录。"""
    roots = [base.data_dir / STAGING_DIRNAME]
    tenants = base.data_dir / TENANTS_DIRNAME
    if tenants.is_dir():
        roots.extend(path / STAGING_DIRNAME for path in sorted(tenants.iterdir()) if path.is_dir())
    return tuple(roots)


def sweep_all(base: Settings, moment: datetime) -> int:
    """启动时清理全部账套的过期会话；单个目录失败只记日志，不影响启动。"""
    removed = 0
    for root in staging_roots(base):
        try:
            removed += sweep_root(root, moment, is_startup=True)
        except OSError:
            logger.exception("清理导入暂存失败：%s", root)
    return removed
