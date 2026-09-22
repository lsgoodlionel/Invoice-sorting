"""搬迁包清单 manifest.json：应用版本、schema 版本、分节统计与逐文件 SHA-256。

清单是导入端唯一可信的目录：解包时只按清单里的条目取文件，
每个条目的大小与校验和都要逐字节核对，zip 头里的信息一律不信。
"""

import json
from dataclasses import dataclass
from datetime import datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version

from invoice_sorting.common.errors import AppError
from invoice_sorting.config import DB_FILENAME, LIBRARY_DIRNAME, PACKAGES_DIRNAME
from invoice_sorting.db.default_keywords import KEYWORDS_VERSION
from invoice_sorting.db.seed import (
    KEYWORDS_VERSION_KEY,
    MEMORY_VERSION,
    MEMORY_VERSION_KEY,
    RULES_VERSION,
    RULES_VERSION_KEY,
)

FORMAT = "invoice-sorting-tenant-export"
FORMAT_VERSION = 1
MANIFEST_NAME = "manifest.json"
DATA_PREFIX = "data/"
UNKNOWN_VERSION = "0.0.0"

SECTION_DATABASE = "database"
SECTION_LIBRARY = "library"
SECTION_PACKAGES = "packages"
SECTION_ACCOUNTS = "accounts"

# 单账套导出时附带的登录账号清单（只含密码哈希，账本搬迁设计 2.1）；与数据库同列在清单里、参与校验
ACCOUNTS_FILENAME = "accounts.json"

# 清单中的 schema 版本键 → 当前程序支持的最高版本
SUPPORTED_SCHEMA: dict[str, int] = {
    KEYWORDS_VERSION_KEY: KEYWORDS_VERSION,
    RULES_VERSION_KEY: RULES_VERSION,
    MEMORY_VERSION_KEY: MEMORY_VERSION,
}

MSG_MANIFEST_MISSING = "搬迁包里没有 manifest.json，不是本工具导出的账套数据包"
MSG_MANIFEST_BROKEN = "搬迁包的 manifest.json 无法解析，文件可能已损坏"
MSG_FORMAT_MISMATCH = "搬迁包格式不符，不是本工具导出的账套数据包"
MSG_VERSION_TOO_NEW = "搬迁包版本过新（格式 {found}，本程序最高支持 {supported}），请先升级程序"
MSG_SCHEMA_TOO_NEW = "搬迁包的 {key} 为 {found}，超出本程序支持的 {supported}，请先升级程序"
MSG_FILES_BROKEN = "搬迁包的文件清单结构不正确，文件可能已损坏"
MSG_NO_DATABASE = "搬迁包里没有数据库快照，无法导入"


def app_version() -> str:
    """已安装的应用版本；源码运行且未安装时返回占位版本。"""
    try:
        return package_version("invoice-sorting")
    except PackageNotFoundError:
        return UNKNOWN_VERSION


def section_of(relative_path: str) -> str:
    """按相对租户数据目录的路径判断所属部分。"""
    if relative_path == ACCOUNTS_FILENAME:
        return SECTION_ACCOUNTS
    if relative_path.startswith(f"{LIBRARY_DIRNAME}/"):
        return SECTION_LIBRARY
    if relative_path.startswith(f"{PACKAGES_DIRNAME}/"):
        return SECTION_PACKAGES
    return SECTION_DATABASE


@dataclass(frozen=True)
class FileEntry:
    """一个成员文件：路径相对租户数据目录，大小与校验和用于导入时核对。"""

    path: str
    size: int
    sha256: str

    @property
    def member(self) -> str:
        """在 zip 中的成员名。"""
        return f"{DATA_PREFIX}{self.path}"

    @property
    def section(self) -> str:
        return section_of(self.path)


@dataclass(frozen=True)
class Manifest:
    """搬迁包清单；构造后不再修改。"""

    tenant_slug: str
    tenant_name: str
    exported_at: str
    files: tuple[FileEntry, ...]
    schema_versions: dict[str, str]
    app_version: str = ""
    format_version: int = FORMAT_VERSION

    @property
    def total_bytes(self) -> int:
        return sum(entry.size for entry in self.files)

    @property
    def has_database(self) -> bool:
        return any(entry.path == DB_FILENAME for entry in self.files)

    @property
    def accounts_entry(self) -> FileEntry | None:
        """包内的登录账号清单；SaaS 导出与旧包没有。"""
        return next((entry for entry in self.files if entry.path == ACCOUNTS_FILENAME), None)

    def sections(self) -> dict[str, dict[str, int]]:
        """各部分的文件数与字节数。"""
        summary: dict[str, dict[str, int]] = {}
        for entry in self.files:
            current = summary.get(entry.section, {"files": 0, "bytes": 0})
            summary[entry.section] = {
                "files": current["files"] + 1,
                "bytes": current["bytes"] + entry.size,
            }
        return summary

    def to_bytes(self) -> bytes:
        payload = {
            "format": FORMAT,
            "format_version": self.format_version,
            "app_version": self.app_version,
            "exported_at": self.exported_at,
            "tenant": {"slug": self.tenant_slug, "name": self.tenant_name},
            "schema_versions": dict(self.schema_versions),
            "sections": self.sections(),
            "total_bytes": self.total_bytes,
            "files": [
                {"path": entry.path, "size": entry.size, "sha256": entry.sha256}
                for entry in self.files
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def build_manifest(
    slug: str,
    name: str,
    moment: datetime,
    files: tuple[FileEntry, ...],
    schema_versions: dict[str, str],
) -> Manifest:
    return Manifest(
        tenant_slug=slug,
        tenant_name=name,
        exported_at=moment.isoformat(),
        files=files,
        schema_versions=dict(schema_versions),
        app_version=app_version(),
    )


def parse_manifest(raw: bytes) -> Manifest:
    """解析并校验清单结构；任何不符都给出面向用户的中文原因。"""
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AppError(MSG_MANIFEST_BROKEN) from error
    if not isinstance(payload, dict) or payload.get("format") != FORMAT:
        raise AppError(MSG_FORMAT_MISMATCH)
    found = payload.get("format_version")
    if not isinstance(found, int) or found < 1:
        raise AppError(MSG_MANIFEST_BROKEN)
    if found > FORMAT_VERSION:
        raise AppError(MSG_VERSION_TOO_NEW.format(found=found, supported=FORMAT_VERSION))
    tenant = payload.get("tenant") or {}
    if not isinstance(tenant, dict):
        raise AppError(MSG_MANIFEST_BROKEN)
    return Manifest(
        tenant_slug=str(tenant.get("slug", "")),
        tenant_name=str(tenant.get("name", "")),
        exported_at=str(payload.get("exported_at", "")),
        files=_parse_files(payload.get("files")),
        schema_versions=_parse_schema(payload.get("schema_versions")),
        app_version=str(payload.get("app_version", "")),
        format_version=found,
    )


def _parse_files(rows: object) -> tuple[FileEntry, ...]:
    if not isinstance(rows, list):
        raise AppError(MSG_FILES_BROKEN)
    entries: list[FileEntry] = []
    for row in rows:
        if not isinstance(row, dict):
            raise AppError(MSG_FILES_BROKEN)
        path, size, digest = row.get("path"), row.get("size"), row.get("sha256")
        is_valid = (
            isinstance(path, str)
            and isinstance(size, int)
            and not isinstance(size, bool)
            and size >= 0
            and isinstance(digest, str)
            and len(digest) == 64
        )
        if not is_valid:
            raise AppError(MSG_FILES_BROKEN)
        entries.append(FileEntry(path=str(path), size=int(size), sha256=str(digest)))
    return tuple(entries)


def _parse_schema(values: object) -> dict[str, str]:
    if values is None:
        return {}
    if not isinstance(values, dict):
        raise AppError(MSG_MANIFEST_BROKEN)
    return {str(key): str(value) for key, value in values.items()}


def check_schema_supported(manifest: Manifest) -> None:
    """拒绝由更新版本程序导出的数据（本程序看不懂新版种子与规则）。"""
    for key, supported in SUPPORTED_SCHEMA.items():
        raw = manifest.schema_versions.get(key, "")
        if not raw.isdigit():
            continue  # 老包或未记录该版本：交给启动时的补列与种子逻辑处理
        if int(raw) > supported:
            raise AppError(MSG_SCHEMA_TOO_NEW.format(key=key, found=raw, supported=supported))
