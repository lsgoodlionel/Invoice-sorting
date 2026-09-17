"""文件系统操作日志：数据库回滚时把本次移动/新建的文件与目录撤销回原位。"""

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FsJournal:
    _steps: list[tuple[str, Path, Path | None]] = field(default_factory=list)

    def moved(self, source: Path, destination: Path) -> None:
        if source != destination:
            self._steps.append(("move", source, destination))

    def created_dir(self, directory: Path) -> None:
        self._steps.append(("mkdir", directory, None))

    def undo(self) -> None:
        """逆序撤销；单步失败只记录日志，尽量恢复其余步骤。"""
        for action, first, second in reversed(self._steps):
            try:
                if action == "move" and second is not None and second.exists():
                    first.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(second, first)
                elif action == "mkdir" and first.is_dir() and not any(first.iterdir()):
                    first.rmdir()
            except OSError:
                logger.exception("撤销文件操作失败：%s %s → %s", action, first, second)
        self._steps.clear()
