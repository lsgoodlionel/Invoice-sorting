"""占位账号（账本搬迁设计 4.3）：包里的上传人/操作人在本地找不到时，建一个停用账号保留姓名。

- 控制库：`account`（停用、无密码、source=import）+ 本账套的 `membership`（停用），
  因此会出现在用户管理里并标注“来自导入”；
- 业务库：同 id 的 `app_user` 镜像（停用），历史记录仍显示“谁传的、谁改的”。
用户名全局唯一：原用户名被占用时改用 `原名.imp`、`原名.imp2`……，不与任何现有账号合并，
避免把别的账套的账号拉进本账套。
"""

import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from invoice_sorting.control.models import (
    ACCOUNT_SOURCE_IMPORT,
    ROLE_MEMBER,
    Account,
    ControlAuthSession,
    Membership,
)
from invoice_sorting.db.models import User, now
from invoice_sorting.migration.merge_plan import Placeholder

logger = logging.getLogger(__name__)

USERNAME_MAX = 32
USERNAME_MIN = 3
SUFFIX = ".imp"
FALLBACK_NAME = "imported"
DISPLAY_NAME_MAX = 32
ILLEGAL_USERNAME_CHARS = re.compile(r"[^a-z0-9_.\-]")


@dataclass(frozen=True)
class CreatedPlaceholder:
    package_id: int
    account_id: int
    username: str
    display_name: str


def placeholder_username(original: str, is_taken: Callable[[str], bool]) -> str:
    """原名可用就用原名；否则追加 .imp / .imp2 …；总长不超过 32。"""
    base = ILLEGAL_USERNAME_CHARS.sub("", (original or "").lower())[:USERNAME_MAX]
    if len(base) < USERNAME_MIN:
        base = FALLBACK_NAME
    if not is_taken(base):
        return base
    sequence = 1
    while True:
        tail = SUFFIX if sequence == 1 else f"{SUFFIX}{sequence}"
        candidate = f"{base[: USERNAME_MAX - len(tail)]}{tail}"
        if not is_taken(candidate):
            return candidate
        sequence += 1


def create_placeholders(
    control: Session, business: Session, tenant_id: int, placeholders: Iterable[Placeholder]
) -> tuple[CreatedPlaceholder, ...]:
    """在两个库里各建一行（只 flush，不提交；提交与回滚由调用方统一处理）。"""
    created: list[CreatedPlaceholder] = []
    for item in placeholders:
        username = placeholder_username(item.username, _taken_checker(control, business))
        display_name = (item.display_name or username)[:DISPLAY_NAME_MAX]
        account = Account(
            username=username,
            display_name=display_name,
            password_hash=None,
            is_active=False,
            source=ACCOUNT_SOURCE_IMPORT,
        )
        control.add(account)
        control.flush()
        control.add(
            Membership(
                account_id=account.id, tenant_id=tenant_id, role=ROLE_MEMBER, is_active=False
            )
        )
        business.add(
            User(
                id=account.id,
                username=username,
                display_name=display_name,
                role=ROLE_MEMBER,
                is_active=False,
                created_at=now(),
            )
        )
        control.flush()
        business.flush()
        created.append(CreatedPlaceholder(item.package_id, account.id, username, display_name))
    return tuple(created)


def _taken_checker(control: Session, business: Session) -> Callable[[str], bool]:
    def is_taken(name: str) -> bool:
        in_control = control.scalar(select(Account.id).where(Account.username == name))
        in_business = business.scalar(select(User.id).where(User.username == name))
        return in_control is not None or in_business is not None

    return is_taken


def remove_placeholders(factory: sessionmaker[Session], account_ids: Iterable[int]) -> None:
    """补偿：业务库提交失败而控制库已提交时，删掉本次建的占位账号与成员关系。"""
    ids = list(account_ids)
    if not ids:
        return
    with factory() as control:
        control.execute(delete(ControlAuthSession).where(ControlAuthSession.account_id.in_(ids)))
        control.execute(delete(Membership).where(Membership.account_id.in_(ids)))
        control.execute(
            delete(Account).where(Account.id.in_(ids), Account.source == ACCOUNT_SOURCE_IMPORT)
        )
        control.commit()
    logger.warning("合并导入失败，已撤销占位账号 %s 个", len(ids))
