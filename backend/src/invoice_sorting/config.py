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
LOGS_DIRNAME = "日志"
DIAGNOSTICS_DIRNAME = "诊断包"
LOG_FILENAME = "app.log"
DB_FILENAME = "invoice.db"
CONTROL_DB_FILENAME = "control.db"
TENANTS_DIRNAME = "tenants"
MAX_UPLOAD_BYTES = 30 * 1024 * 1024

MODE_SINGLE = "single"
MODE_SAAS = "saas"
DeploymentMode = Literal["single", "saas"]
DEFAULT_TENANT_SLUG = "default"
# 默认授权服务地址；正式发布时改为自家 SaaS 控制面地址，留空表示不校验
DEFAULT_LICENSE_SERVER = ""
DEFAULT_TENANT_NAME = "默认账套"
# 运行日志与故障上报（设计《日志与故障上报》）：默认只在本机留存，不上传
DEFAULT_LOG_APP = "invoice-sorting"
DEFAULT_LOG_BRANCH = "main"
DEFAULT_LOG_LEVEL = "INFO"


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
    # 私有化授权（设计 6）：两项都留空时不做校验，按本机自用处理
    license_key: str = ""
    license_server: str = DEFAULT_LICENSE_SERVER
    license_check_interval_hours: int = 24
    license_grace_days: int = 14
    # 运行日志与故障上报：log_repo / log_token 两项都配置了才会上传，默认只留在本机
    log_level: str = DEFAULT_LOG_LEVEL
    log_repo: str = ""  # 形如 owner/repo 的**私有**仓库；留空即关闭上传
    log_token: str = ""  # 细粒度 PAT，只从环境变量读，不落库、不进日志、不进诊断包
    log_app: str = DEFAULT_LOG_APP  # 仓库内的应用命名空间（该仓库由多个应用共用）
    log_instance: str = ""  # 实例名，留空时用主机短名
    log_branch: str = DEFAULT_LOG_BRANCH

    @property
    def is_log_upload_configured(self) -> bool:
        """仓库与令牌都配置了才上传；缺任意一项都只在本机生成诊断包。"""
        return bool(self.log_repo.strip() and self.log_token.strip())

    @property
    def is_license_configured(self) -> bool:
        """单租户且配置了密钥与服务地址时才启用在线校验（SaaS 控制面自身不校验）。"""
        return bool(self.license_key and self.license_server) and not self.is_saas

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

    @cached_property
    def logs_dir(self) -> Path:
        return self.data_dir / LOGS_DIRNAME

    @cached_property
    def log_file(self) -> Path:
        return self.logs_dir / LOG_FILENAME

    @cached_property
    def diagnostics_dir(self) -> Path:
        return self.logs_dir / DIAGNOSTICS_DIRNAME

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
