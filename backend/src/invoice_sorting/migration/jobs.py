"""导出后台任务登记表：接口只返回任务号与下载地址，打包在后台线程进行。

任务状态存在进程内存里（重启后作废，重新导出即可），生成的搬迁包落在 `备份/租户导出/`，
每次成功导出后只保留最近 KEEP_EXPORTS 个包，避免备份目录无限增长。
"""

import logging
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from invoice_sorting.common.errors import AppError, NotFoundError
from invoice_sorting.config import Settings
from invoice_sorting.db.models import now

logger = logging.getLogger(__name__)

EXPORTS_DIRNAME = "租户导出"
KEEP_EXPORTS = 5
JOB_CAPACITY = 50

STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

MSG_JOB_NOT_FOUND = "导出任务"
MSG_JOB_UNFINISHED = "导出任务尚未完成"
MSG_JOB_FAILED = "导出任务失败：{reason}"
MSG_FILE_GONE = "导出文件已被清理，请重新导出"


@dataclass(frozen=True)
class ExportJob:
    """一次导出任务；状态变更一律产生新对象，不就地修改。"""

    id: str
    slug: str
    status: str
    created_at: datetime
    path: Path | None = None
    size: int = 0
    file_count: int = 0
    error: str = ""
    include_packages: bool = True

    @property
    def filename(self) -> str:
        return self.path.name if self.path is not None else ""


class ExportJobStore:
    """线程安全的任务登记表，超出容量时丢弃最早的任务记录（文件另有清理策略）。"""

    def __init__(self, capacity: int = JOB_CAPACITY) -> None:
        self._jobs: OrderedDict[str, ExportJob] = OrderedDict()
        self._capacity = max(1, capacity)
        self._lock = threading.RLock()

    def create(self, slug: str, include_packages: bool = True) -> ExportJob:
        job = ExportJob(
            id=uuid.uuid4().hex,
            slug=slug,
            status=STATUS_RUNNING,
            created_at=now(),
            include_packages=include_packages,
        )
        with self._lock:
            self._jobs[job.id] = job
            while len(self._jobs) > self._capacity:
                self._jobs.popitem(last=False)
        return job

    def find(self, job_id: str) -> ExportJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def require(self, job_id: str, slug: str) -> ExportJob:
        """取任务并确认属于该账套，避免跨账套拿到别人的搬迁包。"""
        job = self.find(job_id)
        if job is None or job.slug != slug:
            raise NotFoundError(MSG_JOB_NOT_FOUND)
        return job

    def finish(self, job_id: str, path: Path, file_count: int) -> None:
        self._update(
            job_id,
            status=STATUS_DONE,
            path=path,
            size=_size_of(path),
            file_count=file_count,
        )

    def fail(self, job_id: str, reason: str) -> None:
        self._update(job_id, status=STATUS_FAILED, error=reason)

    def _update(self, job_id: str, **changes: object) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            self._jobs[job_id] = replace(job, **changes)


def _size_of(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def exports_dir(settings: Settings) -> Path:
    """搬迁包输出目录（部署根目录下的备份区，不随单个租户目录被覆盖）。"""
    return settings.backup_dir / EXPORTS_DIRNAME


def prune_exports(directory: Path, keep: int = KEEP_EXPORTS) -> None:
    """只保留最近 keep 个搬迁包。"""
    if not directory.is_dir():
        return
    packages = sorted(directory.glob("*.zip"), key=lambda path: path.stat().st_mtime)
    for old in packages[:-keep]:
        try:
            old.unlink()
        except OSError:
            logger.warning("清理旧搬迁包失败：%s", old)
        else:
            logger.info("已清理旧搬迁包 %s", old.name)


def require_download(job: ExportJob) -> Path:
    """取可下载的文件路径；未完成、失败或文件已清理都给出明确中文原因。"""
    if job.status == STATUS_FAILED:
        raise AppError(MSG_JOB_FAILED.format(reason=job.error or "未知原因"))
    if job.status != STATUS_DONE or job.path is None:
        raise AppError(MSG_JOB_UNFINISHED, status_code=409)
    if not job.path.is_file():
        raise AppError(MSG_FILE_GONE, status_code=410)
    return job.path
