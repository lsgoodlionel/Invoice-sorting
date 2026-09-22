"""搬迁包只读检查与数据库快照打开：合并导入与预览共用。

- `inspect_package` 只读 manifest.json、ledger.json 与（若有）accounts.json，
  做版本、清单、体积与校验和体检，不落盘；报告里只给账号个数，不带任何哈希；
- `open_package_db` 把包内数据库快照解到暂存目录（逐字节核对校验和），
  补齐旧版本缺的列后以独立引擎打开，用完即释放。包内库只读，从不写回业务库。
"""

import logging
import zipfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from invoice_sorting.common.errors import AppError
from invoice_sorting.config import DB_FILENAME
from invoice_sorting.db.session import create_db_engine, init_db, make_session_factory
from invoice_sorting.migration.accounts_file import AccountsFile, read_accounts
from invoice_sorting.migration.archive import extract_entry, open_archive, read_member
from invoice_sorting.migration.errors import ImportRejectedError
from invoice_sorting.migration.ledger import LEDGER_MAX_BYTES, LEDGER_NAME, LedgerInfo, parse_ledger
from invoice_sorting.migration.manifest import FileEntry, Manifest
from invoice_sorting.migration.restore import read_manifest

logger = logging.getLogger(__name__)

FALLBACK_SOURCE_LABEL = "搬迁包"
MSG_PACKAGE_DB_BROKEN = "搬迁包里的数据库无法打开：{reason}"


@dataclass(frozen=True)
class PackageInfo:
    """一个已通过体检的搬迁包：清单与（新包才有的）账本描述。"""

    path: Path
    manifest: Manifest
    ledger: LedgerInfo | None
    # 包内的登录账号清单（已核对校验和）；SaaS 导出与旧包为 None
    accounts: AccountsFile | None = None

    @property
    def account_count(self) -> int:
        return self.accounts.count if self.accounts is not None else 0

    @property
    def is_legacy(self) -> bool:
        """没有 ledger.json 的旧包：按整账套包处理。"""
        return self.ledger is None

    @property
    def source_label(self) -> str:
        """来源名称：用于批次改名后缀与报告，依次取账本来源、清单账套名、账套标识。"""
        if self.ledger is not None and self.ledger.source.tenant:
            return self.ledger.source.tenant
        return self.manifest.tenant_name or self.manifest.tenant_slug or FALLBACK_SOURCE_LABEL

    def entries_by_path(self) -> Mapping[str, FileEntry]:
        return MappingProxyType({entry.path: entry for entry in self.manifest.files})

    def summary(self) -> dict[str, object]:
        """报告里的来源信息（不含任何令牌或本机路径）；旧包没有的字段为空串。"""
        source = self.ledger.source if self.ledger is not None else None
        return {
            "tenant": self.source_label,
            "exported_by": source.exported_by if source else "",
            "deployment": source.deployment if source else "",
            "app_version": (source.app_version if source else "") or self.manifest.app_version,
            "exported_at": self.manifest.exported_at,
            "is_legacy": self.is_legacy,
            "file_count": len(self.manifest.files),
            "total_bytes": self.manifest.total_bytes,
            "has_accounts": self.accounts is not None,
            "account_count": self.account_count,
            "scope": self.ledger.to_dict()["scope"] if self.ledger is not None else None,
        }


def inspect_package(archive_path: Path) -> PackageInfo:
    """只读体检：清单结构、格式与 schema 版本、成员路径与体积、账本描述。"""
    try:
        manifest = read_manifest(archive_path)
        with open_archive(archive_path) as archive:
            ledger = _read_ledger(archive)
        accounts = read_accounts(archive_path, manifest)
    except ImportRejectedError:
        raise
    except AppError as error:
        raise ImportRejectedError(error.message, status_code=error.status_code) from error
    return PackageInfo(path=archive_path, manifest=manifest, ledger=ledger, accounts=accounts)


def _read_ledger(archive: zipfile.ZipFile) -> LedgerInfo | None:
    if LEDGER_NAME not in archive.namelist():
        return None
    return parse_ledger(read_member(archive, LEDGER_NAME, LEDGER_MAX_BYTES))


@contextmanager
def open_package_db(info: PackageInfo, workdir: Path) -> Iterator[sessionmaker[Session]]:
    """解出包内数据库快照并打开；退出时释放连接（暂存目录由调用方清理）。"""
    entry = info.entries_by_path().get(DB_FILENAME)
    if entry is None:  # read_manifest 已校验，这里只防御
        raise ImportRejectedError(MSG_PACKAGE_DB_BROKEN.format(reason="缺少数据库快照"))
    target = workdir / DB_FILENAME
    try:
        with open_archive(info.path) as archive:
            extract_entry(archive, entry, target)
    except AppError as error:
        raise ImportRejectedError(error.message) from error
    engine = create_db_engine(f"sqlite:///{target}")
    try:
        factory = _prepare(engine, info)
        yield factory
    finally:
        engine.dispose()


def _prepare(engine: Engine, info: PackageInfo) -> sessionmaker[Session]:
    """补齐旧版本导出的库缺少的列；库文件本身损坏时视为校验失败。"""
    try:
        init_db(engine)
    except SQLAlchemyError as error:
        logger.exception("打开搬迁包数据库失败：%s", info.path)
        reason = type(error).__name__
        raise ImportRejectedError(MSG_PACKAGE_DB_BROKEN.format(reason=reason)) from error
    return make_session_factory(engine)
