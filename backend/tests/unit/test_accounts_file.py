"""accounts.json 的格式与校验：包来自外部，字段逐一核对；哈希不出现在 repr 里。测试数据全部虚构。"""

import json

import pytest

from invoice_sorting.common.errors import AppError
from invoice_sorting.migration.accounts_file import AccountRecord, AccountsFile, parse_accounts
from invoice_sorting.migration.ledger import LedgerInfo, LedgerScope, LedgerSource, parse_ledger
from invoice_sorting.migration.manifest import (
    ACCOUNTS_FILENAME,
    SECTION_ACCOUNTS,
    FileEntry,
    section_of,
)

FAKE_HASH = "scrypt$n=16384,r=8,p=1$ZmFrZXNhbHQ=$ZmFrZWRpZ2VzdA=="


def _record(**overrides) -> dict:
    row = {
        "id": 1,
        "username": "admin",
        "display_name": "虚构管理员",
        "role": "admin",
        "is_active": True,
        "source": "",
        "password_hash": FAKE_HASH,
    }
    return {**row, **overrides}


def _raw(*rows: dict, **top) -> bytes:
    payload = {"kind": "accounts", "version": 1, "tenant": "default", "accounts": list(rows)}
    return json.dumps({**payload, **top}).encode()


def test_roundtrip_keeps_every_field():
    original = AccountsFile(
        tenant="default",
        accounts=(AccountRecord(1, "admin", "虚构管理员", "admin", True, "", FAKE_HASH),),
    )

    parsed = parse_accounts(original.to_bytes())

    assert parsed == original


def test_repr_never_shows_password_hash():
    record = AccountRecord(1, "admin", "虚构管理员", "admin", True, "", FAKE_HASH)

    assert FAKE_HASH not in repr(record)
    assert FAKE_HASH not in repr(AccountsFile(tenant="default", accounts=(record,)))


def test_account_without_password_is_allowed():
    parsed = parse_accounts(_raw(_record(password_hash=None)))

    assert parsed.accounts[0].has_password is False


@pytest.mark.parametrize(
    "row",
    [
        _record(id=0),
        _record(id=True),
        _record(id=2**31),
        _record(id="1"),
        _record(username="Admin"),
        _record(username=" admin"),
        _record(username=""),
        _record(username="a\x00b"),
        _record(role="owner"),
        _record(is_active="yes"),
        _record(source="platform"),
        _record(password_hash="含 空 格"),
        _record(password_hash="x" * 300),
        _record(password_hash=123),
        "不是对象",
    ],
)
def test_rejects_malformed_rows(row):
    with pytest.raises(AppError, match="accounts.json"):
        parse_accounts(_raw(row))


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        _raw(kind="other"),
        _raw(version=2),
        json.dumps({"kind": "accounts", "version": 1, "accounts": {}}).encode(),
    ],
)
def test_rejects_malformed_files(raw):
    with pytest.raises(AppError, match="accounts.json"):
        parse_accounts(raw)


def test_rejects_duplicate_ids_and_usernames():
    with pytest.raises(AppError, match="重复"):
        parse_accounts(_raw(_record(), _record(username="alice")))
    with pytest.raises(AppError, match="重复"):
        parse_accounts(_raw(_record(), _record(id=2)))


def test_display_name_is_cleaned_and_falls_back_to_username():
    parsed = parse_accounts(_raw(_record(display_name="\x07"), _record(id=2, username="bob")))

    assert parsed.accounts[0].display_name == "admin"


def test_accounts_file_has_its_own_manifest_section():
    entry = FileEntry(path=ACCOUNTS_FILENAME, size=10, sha256="a" * 64)

    assert section_of(ACCOUNTS_FILENAME) == SECTION_ACCOUNTS
    assert entry.section == SECTION_ACCOUNTS


def test_ledger_has_accounts_roundtrip_and_default():
    info = LedgerInfo(source=LedgerSource(), scope=LedgerScope(), has_accounts=True)

    assert parse_ledger(info.to_bytes()).has_accounts is True
    assert parse_ledger(json.dumps({"kind": "ledger"}).encode()).has_accounts is False
    with pytest.raises(AppError):
        parse_ledger(json.dumps({"kind": "ledger", "has_accounts": "yes"}).encode())


def test_business_usernames_ignore_out_of_range_or_malformed_rows(tmp_path):
    import sqlite3
    from contextlib import closing

    from invoice_sorting.migration.accounts_restore import business_usernames

    db_path = tmp_path / "虚构业务库.db"
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("create table app_user (id integer primary key, username text)")
        conn.executemany(
            "insert into app_user values (?, ?)",
            [(1, "admin"), (-5, "neg"), (2**40, "huge"), (3, "Upper"), (4, None), (5, "ok")],
        )
        conn.commit()

    assert business_usernames(db_path) == {1: "admin", 5: "ok"}
