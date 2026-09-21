"""合并导入的文件侧：从搬迁包取附件（只取清单列出的成员并核对校验和）、按本地规则落盘、失败回滚。

落盘不照搬包内路径：由 `attachments.storage` 按本地文件库规则（记录文件夹名、附件命名）选路径。
本次新建的每个文件与记录文件夹都登记在 FileTracker 里，导入失败时逐一删除，
文件库回到导入前的样子；本地已有文件从不移动、覆盖或删除。
"""

import logging
import shutil
import uuid
import zipfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy.orm import Session

from invoice_sorting.attachments.storage import new_file_destination
from invoice_sorting.common.errors import AppError
from invoice_sorting.config import Settings
from invoice_sorting.db.models import Attachment
from invoice_sorting.migration.archive import extract_entry, open_archive
from invoice_sorting.migration.manifest import FileEntry
from invoice_sorting.migration.package import ImportRejectedError, PackageInfo

logger = logging.getLogger(__name__)

MERGE_STAGING_DIRNAME = ".合并暂存"
MSG_FILE_NOT_LISTED = "搬迁包清单里没有附件文件：{path}"


@contextmanager
def staging_dir(settings: Settings) -> Iterator[Path]:
    """本次导入独占的暂存目录（与数据目录同盘，落盘时可直接改名）；退出时整体删除。

    与整套替换的 `.导入暂存` 分开，避免两种导入或网页上传互相清掉对方的暂存文件。
    """
    root = settings.data_dir / MERGE_STAGING_DIRNAME / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=False)
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)
        _remove_if_empty(root.parent)


def _remove_if_empty(directory: Path) -> None:
    try:
        directory.rmdir()
    except OSError:
        return


class FileTracker:
    """登记本次新建的文件与目录；rollback 时删除文件并清理因此变空的目录。"""

    def __init__(self, library_dir: Path) -> None:
        self._library = library_dir
        self._files: list[Path] = []
        self._dirs: list[Path] = []

    @property
    def file_count(self) -> int:
        return len(self._files)

    def track_file(self, path: Path) -> None:
        self._files.append(path)

    def track_dir(self, path: Path) -> None:
        self._dirs.append(path)

    def rollback(self) -> None:
        for path in reversed(self._files):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.exception("回滚时删除文件失败：%s", path)
        parents = [path.parent for path in self._files] + self._dirs
        for directory in sorted(set(parents), key=lambda item: len(item.parts), reverse=True):
            self._prune(directory)

    def _prune(self, directory: Path) -> None:
        """自下而上删除空目录，止于文件库根目录。"""
        while directory != self._library and self._library in directory.parents:
            try:
                directory.rmdir()
            except OSError:
                return
            directory = directory.parent


class FileSource:
    """按需从搬迁包解出单个附件到暂存目录，逐字节核对清单里的大小与校验和。"""

    def __init__(self, archive: zipfile.ZipFile, info: PackageInfo, staging: Path) -> None:
        self._archive = archive
        self._entries: Mapping[str, FileEntry] = info.entries_by_path()
        self._staging = staging
        self._counter = 0

    def stage(self, file_path: str) -> Path:
        entry = self._entries.get(file_path)
        if entry is None:  # 规划阶段已排除，这里只防御
            raise ImportRejectedError(MSG_FILE_NOT_LISTED.format(path=file_path))
        self._counter += 1
        target = self._staging / f"{self._counter:08d}.part"
        try:
            extract_entry(self._archive, entry, target)
        except AppError as error:
            raise ImportRejectedError(error.message) from error
        return target


@contextmanager
def file_source(info: PackageInfo, staging: Path) -> Iterator[FileSource]:
    with open_archive(info.path) as archive:
        yield FileSource(archive, info, staging)


def place_file(
    db: Session, settings: Settings, attachment: Attachment, staged: Path, tracker: FileTracker
) -> None:
    """附件已 flush 且发票数据已挂好（命名要用发票号）后调用：选路径 → 登记 → 改名落盘。"""
    destination = new_file_destination(db, settings, attachment)
    tracker.track_file(destination)
    shutil.move(str(staged), str(destination))
    attachment.file_path = destination.relative_to(settings.data_dir).as_posix()
