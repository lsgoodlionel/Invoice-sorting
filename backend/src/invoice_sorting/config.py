"""应用配置。数据目录可通过环境变量 INVOICE_SORTING_DATA_DIR 覆盖。"""

from functools import cached_property
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

INBOX_DIRNAME = "收件箱"
LIBRARY_DIRNAME = "文件库"
PACKAGES_DIRNAME = "资料包"
BACKUP_DIRNAME = "备份"
TRASH_DIRNAME = ".回收站"
DB_FILENAME = "invoice.db"
MAX_UPLOAD_BYTES = 30 * 1024 * 1024


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INVOICE_SORTING_")

    data_dir: Path = Path.home() / "InvoiceSorting"
    host: str = "127.0.0.1"
    port: int = 8765
    open_browser: bool = True
    watch_inbox: bool = True
    frontend_dist: Path | None = None

    @cached_property
    def db_path(self) -> Path:
        return self.data_dir / DB_FILENAME

    @cached_property
    def inbox_dir(self) -> Path:
        return self.data_dir / INBOX_DIRNAME

    @cached_property
    def library_dir(self) -> Path:
        return self.data_dir / LIBRARY_DIRNAME

    @cached_property
    def trash_dir(self) -> Path:
        return self.library_dir / TRASH_DIRNAME

    @cached_property
    def packages_dir(self) -> Path:
        return self.data_dir / PACKAGES_DIRNAME

    @cached_property
    def backup_dir(self) -> Path:
        return self.data_dir / BACKUP_DIRNAME

    def ensure_dirs(self) -> None:
        for path in (
            self.data_dir,
            self.inbox_dir,
            self.library_dir,
            self.trash_dir,
            self.packages_dir,
            self.backup_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
