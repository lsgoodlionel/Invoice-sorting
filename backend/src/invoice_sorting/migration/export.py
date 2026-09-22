"""租户数据导出（设计 7）：数据库一致快照 + 文件库 + 资料包，逐文件写校验和。

- 数据库用 `VACUUM INTO` 生成快照，不直接拷贝正在写入的 db 文件，也不改动源库的 WAL；
- 文件逐个流式写入 zip，大库不会整包读进内存；
- 收件箱与备份目录不导出（前者是临时投递区，后者是本机历史备份）；
- 根目录另写 ledger.json（账本搬迁设计 2）：来源与导出范围，供合并导入的报告与批次改名使用；
- 单账套部署由调用方传入 accounts（账本搬迁设计 2.1），写成 `accounts.json` 列入清单、参与校验；
  日志只记账号个数，绝不打印密码哈希。
"""

import logging
import os
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from invoice_sorting.common.errors import AppError
from invoice_sorting.config import DB_FILENAME, Settings
from invoice_sorting.db.models import AppSetting, now
from invoice_sorting.db.seed import KEYWORDS_VERSION_KEY, MEMORY_VERSION_KEY, RULES_VERSION_KEY
from invoice_sorting.migration.accounts_file import AccountsFile
from invoice_sorting.migration.archive import add_bytes, add_file, walk_files
from invoice_sorting.migration.ledger import (
    LEDGER_NAME,
    LedgerInfo,
    LedgerSource,
    scope_of_snapshot,
)
from invoice_sorting.migration.manifest import (
    ACCOUNTS_FILENAME,
    DATA_PREFIX,
    MANIFEST_NAME,
    FileEntry,
    Manifest,
    app_version,
    build_manifest,
)
from invoice_sorting.tenancy.runtime import TenantContext

logger = logging.getLogger(__name__)

TEMP_SUFFIX = ".part"
SCHEMA_KEYS = (KEYWORDS_VERSION_KEY, RULES_VERSION_KEY, MEMORY_VERSION_KEY)
MSG_SNAPSHOT_FAILED = "生成数据库快照失败"


@dataclass(frozen=True)
class ExportResult:
    """导出结果：搬迁包路径与写入包中的清单。"""

    path: Path
    manifest: Manifest

    @property
    def file_count(self) -> int:
        return len(self.manifest.files)

    @property
    def total_bytes(self) -> int:
        return self.manifest.total_bytes


def export_filename(slug: str, moment: datetime, token: str = "") -> str:
    """搬迁包文件名；slug 已在上游校验，token 用任务号保证同一秒内多次导出不互相覆盖。"""
    suffix = f"_{token}" if token else ""
    return f"账套_{slug}_{moment:%Y%m%d_%H%M%S}{suffix}.zip"


def export_tenant(  # noqa: PLR0913 - 与导出选项一一对应
    context: TenantContext,
    out_path: Path,
    tenant_name: str = "",
    include_packages: bool = True,
    moment: datetime | None = None,
    exported_by: str = "",
    accounts: AccountsFile | None = None,
) -> ExportResult:
    """导出一个租户的全部数据到 out_path；先写临时文件再原子改名。

    accounts 只在单账套部署由调用方传入（见 accounts_export.collect_accounts）。
    """
    moment = moment or now()
    settings = context.settings
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temp = out_path.with_name(out_path.name + TEMP_SUFFIX)
    try:
        with tempfile.TemporaryDirectory(dir=out_path.parent) as workdir:
            snapshot = Path(workdir) / DB_FILENAME
            snapshot_database(context.engine, snapshot)
            source = LedgerSource(
                deployment=settings.deployment_mode,
                tenant=tenant_name or context.slug,
                exported_by=exported_by,
                app_version=app_version(),
            )
            ledger = LedgerInfo(
                source=source,
                scope=scope_of_snapshot(snapshot),
                has_accounts=accounts is not None,
            )
            entries = _write_archive(temp, settings, snapshot, include_packages, accounts)
        manifest = build_manifest(
            context.slug,
            tenant_name or context.slug,
            moment,
            entries,
            _schema_versions(context.session_factory),
        )
        _append_metadata(temp, manifest, ledger)
        os.replace(temp, out_path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    logger.info(
        "账套 %s 已导出：%s（%s 个文件，登录账号 %s 个）",
        context.slug,
        out_path,
        len(manifest.files),
        accounts.count if accounts is not None else 0,
    )
    return ExportResult(path=out_path, manifest=manifest)


def snapshot_database(engine: Engine, target: Path) -> None:
    """VACUUM INTO 生成一致快照：源库不受影响，WAL 也不被截断或删除。"""
    raw = engine.raw_connection()
    try:
        driver = raw.driver_connection
        if driver is None:  # pragma: no cover - 仅防御非 sqlite 驱动
            raise AppError(MSG_SNAPSHOT_FAILED)
        driver.commit()  # VACUUM 不能在事务中执行，先结束 pysqlite 的隐式事务
        driver.execute("VACUUM INTO ?", (str(target),))
    except sqlite3.Error as error:
        raise AppError(f"{MSG_SNAPSHOT_FAILED}：{error}") from error
    finally:
        raw.close()


def _sources(settings: Settings, snapshot: Path, include_packages: bool) -> list[tuple[Path, str]]:
    """(源文件, 相对租户数据目录的路径)。数据库用快照代替原文件。"""
    items: list[tuple[Path, str]] = [(snapshot, DB_FILENAME)]
    directories = [settings.library_dir]
    if include_packages:
        directories.append(settings.packages_dir)
    for directory in directories:
        for path in walk_files(directory):
            items.append((path, path.relative_to(settings.data_dir).as_posix()))
    return items


def _write_archive(
    temp: Path,
    settings: Settings,
    snapshot: Path,
    include_packages: bool,
    accounts: AccountsFile | None,
) -> tuple[FileEntry, ...]:
    entries: list[FileEntry] = []
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source, relative in _sources(settings, snapshot, include_packages):
            try:
                size, digest = add_file(archive, source, f"{DATA_PREFIX}{relative}")
            except OSError:
                logger.warning("文件读取失败，未打包：%s", source)
                continue
            entries.append(FileEntry(path=relative, size=size, sha256=digest))
        if accounts is not None:
            member = f"{DATA_PREFIX}{ACCOUNTS_FILENAME}"
            size, digest = add_bytes(archive, accounts.to_bytes(), member)
            entries.append(FileEntry(path=ACCOUNTS_FILENAME, size=size, sha256=digest))
    return tuple(entries)


def _append_metadata(temp: Path, manifest: Manifest, ledger: LedgerInfo) -> None:
    """清单在全部文件写完后追加（校验和此时才算得出来）；账本描述 ledger.json 一并写入。"""
    with zipfile.ZipFile(temp, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(LEDGER_NAME, ledger.to_bytes())
        archive.writestr(MANIFEST_NAME, manifest.to_bytes())


def _schema_versions(factory: sessionmaker[Session]) -> dict[str, str]:
    """沿用业务库里的版本标记（keywords_version / rules_version / …）。"""
    with factory() as db:
        rows = {key: db.get(AppSetting, key) for key in SCHEMA_KEYS}
    return {key: (row.value if row is not None else "") for key, row in rows.items()}
