"""应用配置。数据目录可通过环境变量 INVOICE_SORTING_DATA_DIR 覆盖。

部署形态由 INVOICE_SORTING_DEPLOYMENT_MODE 决定（single 单租户 / saas 多租户），
单租户模式下 default 租户直接使用 data_dir 根目录，老部署升级后文件位置不变。
"""

from functools import cached_property
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

INBOX_DIRNAME = "收件箱"
LIBRARY_DIRNAME = "文件库"
PACKAGES_DIRNAME = "资料包"
BACKUP_DIRNAME = "备份"
TRASH_DIRNAME = ".回收站"
DB_FILENAME = "invoice.db"
CONTROL_DB_FILENAME = "control.db"
TENANTS_DIRNAME = "tenants"
MAX_UPLOAD_BYTES = 30 * 1024 * 1024

MODE_SINGLE = "single"
MODE_SAAS = "saas"
DeploymentMode = Literal["single", "saas"]
DEFAULT_TENANT_SLUG = "default"
DEFAULT_TENANT_NAME = "默认账套"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="INVOICE_SORTING_")

    data_dir: Path = Path.home() / "InvoiceSorting"
    host: str = "127.0.0.1"
    port: int = 8765
    open_browser: bool = True
    watch_inbox: bool = True
    frontend_dist: Path | None = None
    auth_enabled: bool = True  # 应用内登录认证；仅本机单人使用时可关闭
    deployment_mode: DeploymentMode = MODE_SINGLE
    tenant_host_suffix: str = ""  # 配置后 t1.example.com 直接定位租户 t1（仅 SaaS 模式）

    @property
    def is_saas(self) -> bool:
        return self.deployment_mode == MODE_SAAS

    @cached_property
    def control_db_path(self) -> Path:
        """控制库：租户、账号、会话、套餐与授权；两种形态都存在。"""
        return self.data_dir / CONTROL_DB_FILENAME

    def tenant_data_dir(self, slug: str) -> Path:
        """租户数据目录。单租户模式的 default 沿用 data_dir 根目录，老部署无需搬动文件。"""
        if not self.is_saas and slug == DEFAULT_TENANT_SLUG:
            return self.data_dir
        return self.data_dir / TENANTS_DIRNAME / slug

    def for_tenant(self, slug: str) -> "Settings":
        """派生该租户的配置副本（不修改自身）；目录与当前一致时直接复用。"""
        target = self.tenant_data_dir(slug)
        if target == self.data_dir:
            return self
        return Settings(**{**self.model_dump(), "data_dir": target})

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
