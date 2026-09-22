"""登录账号随备份走的测试辅助：两台“机器”、导出带账号的包、改写包内 accounts.json。

测试数据全部虚构：账号名、显示名与密码都是编造的，不对应任何真实人员。
"""

import hashlib
import json
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from invoice_sorting.control.models import Account, ControlAuthSession
from invoice_sorting.db.models import User
from invoice_sorting.main import create_app
from invoice_sorting.migration.accounts_export import collect_accounts
from invoice_sorting.migration.export import export_tenant
from invoice_sorting.migration.restore import import_tenant
from tests.auth_helpers import create_user, login, setup_password
from tests.conftest import make_settings

OLD_ADMIN_PASSWORD = "old-admin-pass-1"
NEW_ADMIN_PASSWORD = "new-admin-pass-2"
ALICE_PASSWORD = "alice-backup-pass"
BOB_PASSWORD = "bob-backup-pass"
CAROL_PASSWORD = "carol-local-pass"
KEEPER_PASSWORD = "keeper-local-pass"
ACCOUNTS_MEMBER = "data/accounts.json"


def machine(root: Path) -> Any:
    """一台启用登录的单账套“机器”（独立数据目录）。"""
    return create_app(make_settings(root, auth_enabled=True))


def prepare_old_machine(client: TestClient) -> None:
    """旧机器：admin + 成员 alice + 管理员 bob（依次得到 id 1、2、3）。"""
    setup_password(client, OLD_ADMIN_PASSWORD)
    create_user(client, "alice", password=ALICE_PASSWORD, display_name="虚构甲")
    create_user(client, "bob", password=BOB_PASSWORD, role="admin", display_name="虚构乙")


def prepare_new_machine(client: TestClient) -> None:
    """新机器：admin 用另一个密码，本地独有成员 carol 占用 id 2（与备份里的 alice 冲突）。"""
    setup_password(client, NEW_ADMIN_PASSWORD)
    create_user(client, "carol", password=CAROL_PASSWORD, display_name="虚构丙")


def export_with_accounts(app: Any, out: Path, slug: str = "default") -> Path:
    """与网页备份、命令行导出相同：单账套带上 accounts.json。"""
    accounts = collect_accounts(app.state.control_session_factory, app.state.settings, slug)
    export_tenant(app.state.tenants.get(slug), out, tenant_name="虚构来源账套", accounts=accounts)
    return out


def replace_import(app: Any, archive: Path, slug: str = "default", actor_id: int | None = None):
    factory = app.state.control_session_factory
    return import_tenant(
        app.state.tenants, factory, archive, slug, overwrite=True, actor_id=actor_id
    )


def can_login(app: Any, username: str, password: str) -> bool:
    with TestClient(app) as client:
        return login(client, password, username).status_code == 200


def find_account(app: Any, username: str) -> Account | None:
    with app.state.control_session_factory() as control:
        return control.scalar(select(Account).where(Account.username == username))


def mirror_user(app: Any, user_id: int) -> User | None:
    with app.state.tenants.get("default").session_factory() as db:
        return db.get(User, user_id)


def session_account_ids(app: Any) -> set[int]:
    with app.state.control_session_factory() as control:
        return {row.account_id for row in control.scalars(select(ControlAuthSession))}


def rewrite_accounts(archive: Path, out: Path, mutate: Callable[[list[dict]], list[dict]]) -> Path:
    """复制搬迁包并改写 accounts.json，同步清单里的大小与校验和（模拟另一份合法备份）。"""
    with zipfile.ZipFile(archive) as source:
        manifest = json.loads(source.read("manifest.json"))
        payload = json.loads(source.read(ACCOUNTS_MEMBER))
        raw = json.dumps({**payload, "accounts": mutate(payload["accounts"])}).encode()
        digest = hashlib.sha256(raw).hexdigest()
        files = [
            {**row, "size": len(raw), "sha256": digest} if row["path"] == "accounts.json" else row
            for row in manifest["files"]
        ]
        replaced = {
            "manifest.json": json.dumps({**manifest, "files": files}).encode(),
            ACCOUNTS_MEMBER: raw,
        }
        with zipfile.ZipFile(out, "w") as target:
            for info in source.infolist():
                target.writestr(info.filename, replaced.get(info.filename) or source.read(info))
    return out


def read_package_accounts(archive: Path) -> list[dict]:
    with zipfile.ZipFile(archive) as package:
        return json.loads(package.read(ACCOUNTS_MEMBER))["accounts"]
