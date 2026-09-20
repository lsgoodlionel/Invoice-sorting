"""授权服务：编排“取令牌 → 验签 → 落库 → 推导状态”。

线程安全：后台定时线程与请求线程都会读写快照，统一在锁内整体替换。
未配置授权（或多租户模式）时既不联网也不落库，run_check 直接返回当前状态。
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from invoice_sorting.common.errors import AppError
from invoice_sorting.config import Settings
from invoice_sorting.control.models import Account, Tenant
from invoice_sorting.db.models import now
from invoice_sorting.licensing import client as license_client
from invoice_sorting.licensing.client import VerifyOutcome, VerifyRequest
from invoice_sorting.licensing.constants import (
    MSG_RECHECK_TOO_OFTEN,
    MSG_SERVER_UNREACHABLE,
    MSG_TOKEN_INVALID,
    app_version,
)
from invoice_sorting.licensing.keys import load_public_key
from invoice_sorting.licensing.state import LicenseSnapshot, LicenseStatus, resolve_status
from invoice_sorting.licensing.storage import (
    hash_license_key,
    load_snapshot,
    read_or_create_instance_id,
    save_snapshot,
)
from invoice_sorting.licensing.token import LicenseTokenError, decode_token, verify_claims

logger = logging.getLogger(__name__)

RECHECK_COOLDOWN_SECONDS = 60.0

Verifier = Callable[[str, VerifyRequest], VerifyOutcome]


class LicenseService:
    """私有化实例侧的授权客户端入口。"""

    def __init__(
        self,
        settings: Settings,
        control_factory: sessionmaker[Session],
        verifier: Verifier | None = None,
        clock: Callable[[], datetime] = now,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._factory = control_factory
        self._verifier = verifier
        self._clock = clock
        self._monotonic = monotonic
        self._lock = threading.RLock()
        self._snapshot = LicenseSnapshot(created_at=clock())
        self._instance_id = ""
        self._last_recheck: float | None = None

    @property
    def is_enabled(self) -> bool:
        return self._settings.is_license_configured

    @property
    def instance_id(self) -> str:
        return self._instance_id

    def start(self) -> None:
        """启动时读取实例标识与本地授权记录；不联网，失败不影响应用启动。"""
        if self._settings.is_saas:
            return
        try:
            self._instance_id = read_or_create_instance_id(self._settings)
            with self._factory() as db:
                stored = load_snapshot(db, self._instance_id)
                self._adopt(db, stored)
        except Exception:  # noqa: BLE001 - 授权模块异常绝不能挡住应用启动
            logger.exception("授权状态初始化失败，本次启动按宽限处理")

    def status(self) -> LicenseStatus:
        with self._lock:
            return resolve_status(self._settings, self._snapshot, self._clock())

    def run_check(self) -> LicenseStatus:
        """执行一次在线校验（会发起网络请求），并把结果落库。"""
        if not self.is_enabled:
            return self.status()
        outcome = self._verify()
        moment = self._clock()
        with self._lock:
            updated = self._merge(self._snapshot, outcome, moment)
            self._store(updated)
            return resolve_status(self._settings, updated, moment)

    def recheck(self) -> LicenseStatus:
        """手动复检：限制频率，避免被反复触发拖垮授权服务。"""
        current = self._monotonic()
        with self._lock:
            previous = self._last_recheck
            if previous is not None and current - previous < RECHECK_COOLDOWN_SECONDS:
                raise AppError(MSG_RECHECK_TOO_OFTEN, status_code=429)
            self._last_recheck = current
        return self.run_check()

    def _adopt(self, db: Session, stored: LicenseSnapshot) -> None:
        """采用本地记录；配置换了授权密钥时丢弃旧令牌并重新起算宽限期。"""
        expected = hash_license_key(self._settings.license_key)
        is_same_key = not stored.license_key_hash or stored.license_key_hash == expected
        if is_same_key and stored.instance_id == self._instance_id:
            self._snapshot = stored
            return
        logger.info("授权密钥或实例标识已变化，本地授权记录已重置")
        self._snapshot = LicenseSnapshot(
            instance_id=self._instance_id, license_key_hash="", created_at=self._clock()
        )
        save_snapshot(db, self._snapshot)

    def _verify(self) -> VerifyOutcome:
        verifier = self._verifier or license_client.verify_with_server
        request = VerifyRequest(
            license_key=self._settings.license_key,
            instance_id=self._instance_id,
            app_version=app_version(),
            users=self._count_users(),
            tenants=self._count(Tenant),
        )
        try:
            return verifier(self._settings.license_server, request)
        except Exception:  # noqa: BLE001 - 校验失败按不可达处理，不影响使用
            logger.exception("授权校验过程异常")
            return VerifyOutcome(is_reachable=False, error=MSG_SERVER_UNREACHABLE)

    def _count_users(self) -> int:
        """在用账号数：与授权的 max_users 口径一致（停用账号不计）。"""
        query = select(func.count()).select_from(Account).where(Account.is_active.is_(True))
        return self._scalar(query)

    def _count(self, model: type) -> int:
        return self._scalar(select(func.count()).select_from(model))

    def _scalar(self, query) -> int:
        try:
            with self._factory() as db:
                return int(db.scalar(query) or 0)
        except Exception:  # noqa: BLE001 - 统计失败不应中断校验
            logger.exception("统计用量失败")
            return 0

    def _merge(
        self, current: LicenseSnapshot, outcome: VerifyOutcome, moment: datetime
    ) -> LicenseSnapshot:
        """根据校验结果生成新的快照（不修改原快照）。"""
        base = replace(current, instance_id=self._instance_id, last_attempt_at=moment)
        if outcome.is_rejected:
            logger.warning("授权服务判定本机授权无效，已切换为只读")
            return replace(base, is_revoked=True, server_reachable=True, last_error=outcome.error)
        if not outcome.is_reachable:
            return replace(
                base,
                server_reachable=False,
                last_error=outcome.error or MSG_SERVER_UNREACHABLE,
            )
        return self._accept_token(base, outcome.token, moment)

    def _accept_token(self, base: LicenseSnapshot, token: str, moment: datetime) -> LicenseSnapshot:
        try:
            claims = decode_token(token, load_public_key())
            verify_claims(
                claims,
                self._settings.license_key,
                self._instance_id,
                moment,
                base.issued_at,
            )
        except LicenseTokenError as error:
            logger.warning("授权令牌未通过校验：%s", error)
            return replace(base, server_reachable=True, last_error=MSG_TOKEN_INVALID)
        return replace(
            base,
            license_key_hash=hash_license_key(self._settings.license_key),
            valid_until=claims.valid_until,
            max_users=claims.max_users,
            features=dict(claims.features),
            issued_at=claims.issued_at,
            checked_at=moment,
            last_error="",
            server_reachable=True,
            is_revoked=False,
        )

    def _store(self, snapshot: LicenseSnapshot) -> None:
        self._snapshot = snapshot
        try:
            with self._factory() as db:
                save_snapshot(db, snapshot)
        except Exception:  # noqa: BLE001 - 落库失败只影响下次启动的起点
            logger.exception("保存授权状态失败")
