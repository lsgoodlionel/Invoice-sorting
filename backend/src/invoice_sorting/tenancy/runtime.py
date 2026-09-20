"""租户运行时：按 slug 缓存 (Settings, engine, session_factory)。

缓存为线程安全的 LRU，超出容量时驱逐最久未使用的租户并释放其连接池；
首次访问某租户时才建目录、建库与写种子（SaaS 模式下租户业务库按需加载）。
"""

import logging
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from invoice_sorting.config import Settings
from invoice_sorting.tenancy.bootstrap import open_business_db

logger = logging.getLogger(__name__)

DEFAULT_CAPACITY = 32
MSG_CAPACITY_INVALID = "租户缓存容量至少为 1"


@dataclass(frozen=True)
class TenantContext:
    """一个租户的运行时句柄；不可变，取到后可安全跨线程使用。"""

    slug: str
    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]


class TenantRuntime:
    """租户缓存。get() 命中直接返回，未命中时在锁内完成初始化，避免重复建库。"""

    def __init__(
        self,
        base_settings: Settings,
        capacity: int = DEFAULT_CAPACITY,
        on_open: Callable[[TenantContext], None] | None = None,
    ) -> None:
        if capacity < 1:
            raise ValueError(MSG_CAPACITY_INVALID)
        self._base = base_settings
        self._capacity = capacity
        # 首次加载某租户后的回调（用于按 membership 补齐业务库中的用户镜像）
        self._on_open = on_open
        self._contexts: OrderedDict[str, TenantContext] = OrderedDict()
        self._lock = threading.RLock()

    @property
    def base_settings(self) -> Settings:
        return self._base

    def cached_slugs(self) -> tuple[str, ...]:
        """当前缓存中的 slug，按最久未使用到最近使用排列（测试与运维自检用）。"""
        with self._lock:
            return tuple(self._contexts)

    def get(self, slug: str) -> TenantContext:
        """取该租户的运行时；首次访问会建目录、建库并写入种子数据。"""
        with self._lock:
            found = self._contexts.get(slug)
            if found is not None:
                self._contexts.move_to_end(slug)
                return found
            context = self._open(slug)
            self._contexts[slug] = context
            self._evict_overflow()
            return context

    def evict(self, slug: str) -> bool:
        """驱逐并释放该租户的连接池；不在缓存中返回 False。"""
        with self._lock:
            context = self._contexts.pop(slug, None)
        return _dispose(context)

    def close(self) -> None:
        """释放全部租户的连接池（应用关闭时调用）。"""
        with self._lock:
            contexts = list(self._contexts.values())
            self._contexts.clear()
        for context in contexts:
            _dispose(context)

    def _open(self, slug: str) -> TenantContext:
        settings = self._base.for_tenant(slug)
        engine, factory = open_business_db(settings)
        logger.info("已加载租户业务库：%s（%s）", slug, settings.data_dir)
        context = TenantContext(
            slug=slug, settings=settings, engine=engine, session_factory=factory
        )
        self._notify_open(context)
        return context

    def _notify_open(self, context: TenantContext) -> None:
        """首次加载回调失败不应阻断请求：记录后继续（下次登录会再次同步）。"""
        if self._on_open is None:
            return
        try:
            self._on_open(context)
        except Exception:
            logger.exception("租户首次加载回调失败：%s", context.slug)

    def _evict_overflow(self) -> None:
        while len(self._contexts) > self._capacity:
            _, context = self._contexts.popitem(last=False)
            _dispose(context)


def _dispose(context: TenantContext | None) -> bool:
    """释放连接池；已借出的连接归还时才真正关闭，不会打断进行中的请求。"""
    if context is None:
        return False
    try:
        context.engine.dispose()
    except Exception:
        logger.exception("释放租户连接失败：%s", context.slug)
    return True
