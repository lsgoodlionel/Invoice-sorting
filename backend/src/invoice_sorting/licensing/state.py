"""授权状态机（设计 6）：由本地令牌 + 当前时间推导出四种状态。

| 状态 | 含义 | 是否可写 |
| --- | --- | --- |
| `active` | 令牌有效（或永久授权） | 是 |
| `grace` | 令牌已过期但在宽限期内（含从未取得令牌的新实例） | 是，界面提示 |
| `readonly` | 宽限期满，或服务器明确判定密钥无效/停用 | 否 |
| `unlicensed_ok` | 未配置授权密钥或服务地址（本机自用） | 是，不限制 |
| `not_applicable` | 多租户模式，不使用私有化授权 | 是，不限制 |

“网络不可达”不会改变状态：拿不到新令牌只是不刷新有效期，因此自然落入宽限；
只有服务器**明确**判定无效（4xx）才会立刻转只读。
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from invoice_sorting.config import Settings
from invoice_sorting.db.models import now
from invoice_sorting.licensing.constants import (
    MSG_ACTIVE,
    MSG_GRACE,
    MSG_NOT_APPLICABLE,
    MSG_OFFLINE_HINT,
    MSG_READONLY_EXPIRED,
    MSG_READONLY_REVOKED,
    MSG_UNLICENSED_OK,
)

STATE_ACTIVE = "active"
STATE_GRACE = "grace"
STATE_READONLY = "readonly"
STATE_UNLICENSED_OK = "unlicensed_ok"
STATE_NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class LicenseSnapshot:
    """本地保存的授权令牌与最近一次校验结果；整体替换，不就地修改。"""

    instance_id: str = ""
    license_key_hash: str = ""
    valid_until: datetime | None = None
    max_users: int = 0
    features: dict[str, Any] = field(default_factory=dict)
    issued_at: datetime | None = None
    checked_at: datetime | None = None
    last_attempt_at: datetime | None = None
    last_error: str = ""
    server_reachable: bool = True
    is_revoked: bool = False
    created_at: datetime = field(default_factory=now)

    @property
    def has_token(self) -> bool:
        """是否曾经成功取得并验签过令牌。"""
        return self.issued_at is not None


@dataclass(frozen=True)
class LicenseStatus:
    """对外展示的授权状态（/api/license/status 的数据形状）。"""

    state: str
    message: str
    instance_id: str = ""
    valid_until: datetime | None = None
    grace_until: datetime | None = None
    max_users: int = 0
    last_checked_at: datetime | None = None
    last_error: str = ""
    server_reachable: bool = True

    @property
    def is_readonly(self) -> bool:
        return self.state == STATE_READONLY


def resolve_status(
    settings: Settings, snapshot: LicenseSnapshot, moment: datetime
) -> LicenseStatus:
    """纯函数：不访问数据库与网络，便于逐个分支验证。"""
    if settings.is_saas:
        return _status(snapshot, STATE_NOT_APPLICABLE, MSG_NOT_APPLICABLE)
    if not settings.is_license_configured:
        return _status(snapshot, STATE_UNLICENSED_OK, MSG_UNLICENSED_OK)
    grace = timedelta(days=max(0, settings.license_grace_days))
    if snapshot.is_revoked:
        until = _grace_until(snapshot, grace)
        return _status(snapshot, STATE_READONLY, MSG_READONLY_REVOKED, until)
    if not snapshot.has_token:
        return _without_token(snapshot, snapshot.created_at + grace, moment)
    if snapshot.valid_until is None:
        return _status(snapshot, STATE_ACTIVE, MSG_ACTIVE)  # 永久授权
    return _with_token(snapshot, snapshot.valid_until, snapshot.valid_until + grace, moment)


def _without_token(
    snapshot: LicenseSnapshot, grace_until: datetime, moment: datetime
) -> LicenseStatus:
    """从未取得令牌：从本地授权记录建立时间起算宽限，到期转只读。"""
    if moment <= grace_until:
        return _status(snapshot, STATE_GRACE, _offline_aware(snapshot, MSG_GRACE), grace_until)
    return _status(snapshot, STATE_READONLY, MSG_READONLY_EXPIRED, grace_until)


def _with_token(
    snapshot: LicenseSnapshot, valid_until: datetime, grace_until: datetime, moment: datetime
) -> LicenseStatus:
    """令牌已取得：有效期内 active，宽限期内 grace，再往后只读。"""
    if moment <= valid_until:
        return _status(snapshot, STATE_ACTIVE, MSG_ACTIVE, grace_until)
    if moment <= grace_until:
        return _status(snapshot, STATE_GRACE, _offline_aware(snapshot, MSG_GRACE), grace_until)
    return _status(snapshot, STATE_READONLY, MSG_READONLY_EXPIRED, grace_until)


def _grace_until(snapshot: LicenseSnapshot, grace: timedelta) -> datetime:
    anchor = snapshot.valid_until or snapshot.created_at
    return anchor + grace


def _offline_aware(snapshot: LicenseSnapshot, message: str) -> str:
    return message if snapshot.server_reachable else message + MSG_OFFLINE_HINT


def _status(
    snapshot: LicenseSnapshot,
    state: str,
    message: str,
    grace_until: datetime | None = None,
) -> LicenseStatus:
    return LicenseStatus(
        state=state,
        message=message,
        instance_id=snapshot.instance_id,
        valid_until=snapshot.valid_until,
        grace_until=grace_until,
        max_users=snapshot.max_users,
        last_checked_at=snapshot.checked_at,
        last_error=snapshot.last_error,
        server_reachable=snapshot.server_reachable,
    )
