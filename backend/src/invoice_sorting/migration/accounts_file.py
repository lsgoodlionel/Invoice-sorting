"""登录账号清单 accounts.json（账本搬迁设计 2.1）：单账套备份随包带走账号与密码哈希。

- 只含账套成员的：账号 id、用户名、显示名、角色、启用状态、来源标记与**原样的密码哈希**；
  不含会话、邀请码、平台管理员标记、授权、邮件设置与任何明文密码。
- 与业务库同列在 manifest 里（路径 `accounts.json`），读取时逐字节核对大小与 SHA-256，
  并逐字段校验类型与取值：包来自外部，一律视为不可信输入。
- 密码哈希字段不参与 repr，避免被日志或异常信息意外打印出来。
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from invoice_sorting.common.errors import AppError
from invoice_sorting.control.models import ACCOUNT_SOURCE_IMPORT, ROLE_ADMIN, ROLE_MEMBER
from invoice_sorting.control.repository import USERNAME_MAX, normalize_username
from invoice_sorting.migration.archive import open_archive, read_verified
from invoice_sorting.migration.errors import ImportRejectedError
from invoice_sorting.migration.manifest import Manifest

ACCOUNTS_KIND = "accounts"
ACCOUNTS_VERSION = 1
ACCOUNTS_MAX_BYTES = 16 * 1024 * 1024
ACCOUNTS_MAX_COUNT = 10_000
ACCOUNT_ID_MAX = 2**31 - 1  # 账号 id 上限：挡住异常大值，id 对齐时另分配的新 id 也不会溢出
DISPLAY_NAME_MAX = 32
HASH_MAX = 255
ROLES = (ROLE_ADMIN, ROLE_MEMBER)
SOURCES = ("", ACCOUNT_SOURCE_IMPORT)
# 密码哈希按原样搬运（现行为 scrypt$参数$盐$摘要）：这里只限定为可见 ASCII，
# 算法与参数范围由登录校验负责，不认识的格式只会导致该账号密码校验失败
HASH_PATTERN = re.compile(r"^[\x21-\x7e]+$")
USERNAME_PATTERN = re.compile(r"^[^\x00-\x1f\x7f]+$")

MSG_ACCOUNTS_BROKEN = "搬迁包的 accounts.json 无法解析或字段不正确，文件可能已损坏"
MSG_ACCOUNTS_DUPLICATE = "搬迁包的 accounts.json 含重复的账号：{what}"
MSG_ACCOUNTS_TOO_MANY = "搬迁包的 accounts.json 账号过多（{found} 个），超出上限 {limit}"


@dataclass(frozen=True)
class AccountRecord:
    """备份里的一个账号；password_hash 为空表示该账号当时没有设置密码。"""

    id: int
    username: str
    display_name: str
    role: str
    is_active: bool
    source: str = ""
    password_hash: str | None = field(default=None, repr=False)

    @property
    def has_password(self) -> bool:
        return self.password_hash is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
            "is_active": self.is_active,
            "source": self.source,
            "password_hash": self.password_hash,
        }


@dataclass(frozen=True)
class AccountsFile:
    """accounts.json 的内容：来源账套标识与账号列表（按 id 排序）。"""

    tenant: str
    accounts: tuple[AccountRecord, ...]

    @property
    def count(self) -> int:
        return len(self.accounts)

    def to_bytes(self) -> bytes:
        payload = {
            "kind": ACCOUNTS_KIND,
            "version": ACCOUNTS_VERSION,
            "tenant": self.tenant,
            "accounts": [record.to_dict() for record in self.accounts],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def parse_accounts(raw: bytes) -> AccountsFile:
    """解析并校验 accounts.json；任何不符都视为包已损坏。"""
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AppError(MSG_ACCOUNTS_BROKEN) from error
    is_valid = (
        isinstance(payload, dict)
        and payload.get("kind") == ACCOUNTS_KIND
        and payload.get("version") == ACCOUNTS_VERSION
        and isinstance(payload.get("accounts"), list)
        and isinstance(payload.get("tenant", ""), str)
    )
    if not is_valid:
        raise AppError(MSG_ACCOUNTS_BROKEN)
    rows = payload["accounts"]
    if len(rows) > ACCOUNTS_MAX_COUNT:
        raise AppError(MSG_ACCOUNTS_TOO_MANY.format(found=len(rows), limit=ACCOUNTS_MAX_COUNT))
    records = tuple(_parse_record(row) for row in rows)
    _check_unique(records)
    return AccountsFile(tenant=payload.get("tenant", ""), accounts=records)


def _parse_record(row: object) -> AccountRecord:
    if not isinstance(row, dict):
        raise AppError(MSG_ACCOUNTS_BROKEN)
    account_id, username = row.get("id"), row.get("username")
    display_name, role = row.get("display_name", ""), row.get("role")
    is_active, source = row.get("is_active"), row.get("source", "")
    password_hash = row.get("password_hash")
    is_valid = (
        isinstance(account_id, int)
        and not isinstance(account_id, bool)
        and 1 <= account_id <= ACCOUNT_ID_MAX
        and is_valid_username(username)
        and isinstance(display_name, str)
        and role in ROLES
        and isinstance(is_active, bool)
        and source in SOURCES
        and _is_valid_hash(password_hash)
    )
    if not is_valid:
        raise AppError(MSG_ACCOUNTS_BROKEN)
    return AccountRecord(
        id=account_id,
        username=username,
        display_name=_clean_text(display_name)[:DISPLAY_NAME_MAX] or username[:DISPLAY_NAME_MAX],
        role=role,
        is_active=is_active,
        source=source,
        password_hash=password_hash,
    )


def is_valid_username(value: object) -> bool:
    """用户名须已是规范形式（小写、去首尾空白），不含控制字符。"""
    if not isinstance(value, str) or not 1 <= len(value) <= USERNAME_MAX:
        return False
    return normalize_username(value) == value and bool(USERNAME_PATTERN.match(value))


def _is_valid_hash(value: object) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and len(value) <= HASH_MAX and bool(HASH_PATTERN.match(value))


def _clean_text(value: str) -> str:
    return "".join(char for char in value if char.isprintable()).strip()


def _check_unique(records: tuple[AccountRecord, ...]) -> None:
    ids = [record.id for record in records]
    names = [record.username for record in records]
    for what, values in (("id", ids), ("用户名", names)):
        if len(set(values)) != len(values):
            raise AppError(MSG_ACCOUNTS_DUPLICATE.format(what=what))


def read_accounts(archive_path: Path, manifest: Manifest) -> AccountsFile | None:
    """读取包内账号清单（核对校验和）；包里没有时返回 None。错误统一为“校验失败”。"""
    entry = manifest.accounts_entry
    if entry is None:
        return None
    try:
        with open_archive(archive_path) as archive:
            return parse_accounts(read_verified(archive, entry, ACCOUNTS_MAX_BYTES))
    except ImportRejectedError:
        raise
    except AppError as error:
        raise ImportRejectedError(error.message) from error
