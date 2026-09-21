"""网页导入的分片上传会话（设计 5）：元数据与分片都落在账套数据目录下的 `.导入暂存/<upload_id>/`。

- session.json 先写临时文件再原子改名，服务重启后仍能续传或查看结果；
- 收到了哪些分片以磁盘上的分片文件为准，并发上传不同分片不会争写元数据；
- 会话目录位于账套自己的数据目录下，读取时再核对 slug：一个账套碰不到另一个账套的会话；
- upload_id 只接受 32 位十六进制，杜绝借会话号做路径穿越。
"""

import json
import os
import re
import shutil
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from invoice_sorting.common.errors import AppError, ConflictError, NotFoundError
from invoice_sorting.config import Settings
from invoice_sorting.db.models import now
from invoice_sorting.migration.restore import STAGING_DIRNAME

SESSION_FILENAME = "session.json"
PARTS_DIRNAME = "parts"
PACKAGE_FILENAME = "package.zip"

MIB = 1024 * 1024
MAX_PACKAGE_BYTES = 2 * 1024 * MIB
DEFAULT_PART_BYTES = 8 * MIB
MIN_PART_BYTES = 64 * 1024
MAX_PART_BYTES = 64 * MIB
SESSION_TTL = timedelta(hours=24)
UPLOAD_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")

STATUS_UPLOADING = "uploading"
STATUS_READY = "ready"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

WHAT_SESSION = "导入会话"
MSG_TOO_LARGE = "单个账本包不能超过 2 GB，请在服务器上使用命令行 invoice-sorting import-tenant 导入"
MSG_PART_SIZE = "分片大小须在 64 KB 到 64 MB 之间"
MSG_BUSY = "该导入正在处理中，请稍候再试"


@dataclass(frozen=True)
class UploadSession:
    """一次网页导入；状态变更一律产生新对象，不就地修改。"""

    id: str
    slug: str
    filename: str
    total_size: int
    part_size: int
    sha256: str
    created_at: datetime
    status: str = STATUS_UPLOADING
    mode: str = ""
    error: str = ""
    report: dict[str, Any] | None = None

    @property
    def part_count(self) -> int:
        return max(1, -(-self.total_size // self.part_size))

    @property
    def expires_at(self) -> datetime:
        return self.created_at + SESSION_TTL

    def is_expired(self, moment: datetime) -> bool:
        return moment >= self.expires_at

    def part_bytes(self, index: int) -> int:
        """第 index 片应有的字节数：除最后一片外都等于片大小。"""
        if index < self.part_count - 1:
            return self.part_size
        return self.total_size - self.part_size * (self.part_count - 1)

    def to_json(self) -> str:
        payload = {**self.__dict__, "created_at": self.created_at.isoformat()}
        return json.dumps(payload, ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> "UploadSession":
        payload = json.loads(raw)
        return cls(**{**payload, "created_at": datetime.fromisoformat(payload["created_at"])})


def check_limits(total_size: int, part_size: int) -> None:
    """登记时的体积约束：整包 2 GB 以内，分片 64 KB–64 MB。"""
    if total_size > MAX_PACKAGE_BYTES:
        raise AppError(MSG_TOO_LARGE, status_code=400)
    if not MIN_PART_BYTES <= part_size <= MAX_PART_BYTES:
        raise AppError(MSG_PART_SIZE, status_code=400)


def staging_root(base: Settings, slug: str) -> Path:
    """该账套的导入暂存区（在账套自己的数据目录下）。"""
    return base.for_tenant(slug).data_dir / STAGING_DIRNAME


def load_session(directory: Path) -> UploadSession | None:
    """读取会话元数据；缺失或损坏返回 None，由调用方决定清理。"""
    try:
        return UploadSession.from_json((directory / SESSION_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def write_session(directory: Path, session: UploadSession) -> UploadSession:
    """原子写入会话元数据：先写临时文件再改名，读取方不会看到写了一半的内容。"""
    target = directory / SESSION_FILENAME
    temp = target.with_name(f"{SESSION_FILENAME}.{uuid.uuid4().hex}.tmp")
    temp.write_text(session.to_json(), encoding="utf-8")
    os.replace(temp, target)
    return session


class UploadStore:
    """会话的读写入口；同一会话的合并与导入互斥，避免重复执行。"""

    def __init__(self, base: Settings) -> None:
        self._base = base
        self._lock = threading.Lock()
        self._busy: set[str] = set()

    def directory(self, session: UploadSession) -> Path:
        return staging_root(self._base, session.slug) / session.id

    def parts_dir(self, session: UploadSession) -> Path:
        return self.directory(session) / PARTS_DIRNAME

    def package_path(self, session: UploadSession) -> Path:
        return self.directory(session) / PACKAGE_FILENAME

    def create(
        self, slug: str, filename: str, total_size: int, part_size: int, sha256: str
    ) -> UploadSession:
        check_limits(total_size, part_size)
        session = UploadSession(
            id=uuid.uuid4().hex,
            slug=slug,
            filename=filename,
            total_size=total_size,
            part_size=part_size,
            sha256=sha256.lower(),
            created_at=now(),
        )
        self.parts_dir(session).mkdir(parents=True, exist_ok=True)
        return self.save(session)

    def require(self, slug: str, upload_id: str) -> UploadSession:
        """取会话并确认属于该账套；会话号格式不对、不存在或属于别的账套一律 404。"""
        if not UPLOAD_ID_PATTERN.match(upload_id or ""):
            raise NotFoundError(WHAT_SESSION)
        session = load_session(staging_root(self._base, slug) / upload_id)
        if session is None or session.slug != slug or session.id != upload_id:
            raise NotFoundError(WHAT_SESSION)
        return session

    def save(self, session: UploadSession) -> UploadSession:
        return write_session(self.directory(session), session)

    def update(self, session: UploadSession, **changes: Any) -> UploadSession:
        return self.save(replace(session, **changes))

    def discard_parts(self, session: UploadSession) -> None:
        """合并完成后分片已无用，立即删除，暂存区只占一份包的空间。"""
        shutil.rmtree(self.parts_dir(session), ignore_errors=True)

    def discard_data(self, session: UploadSession) -> None:
        """删掉分片与合并后的包，只留元数据（结果仍可查询）。"""
        self.discard_parts(session)
        self.package_path(session).unlink(missing_ok=True)

    def remove(self, session: UploadSession) -> None:
        shutil.rmtree(self.directory(session), ignore_errors=True)

    @contextmanager
    def exclusive(self, session: UploadSession) -> Iterator[None]:
        """同一会话同一时间只允许一个合并/确认操作，已在处理中直接 409。"""
        with self._lock:
            if session.id in self._busy:
                raise ConflictError(MSG_BUSY)
            self._busy.add(session.id)
        try:
            yield
        finally:
            with self._lock:
                self._busy.discard(session.id)
