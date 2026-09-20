"""写操作守卫：只读降级的统一入口。

用法（批次三的套餐额度、租户状态等可直接复用）：

    from invoice_sorting.licensing.guard import WriteBlock, register_write_guard

    def quota_guard(conn) -> WriteBlock | None:
        return WriteBlock(code="quota_exceeded", message="本月新增记录已达套餐上限") or None

    register_write_guard(app, quota_guard)

注册的检查按注册顺序执行，**先命中先返回**；任一命中即整体拒绝写操作（403）。
GET/HEAD、登录、授权自身、备份与导出不受影响。
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from invoice_sorting.common.errors import AppError
from invoice_sorting.licensing.constants import (
    API_PREFIX,
    WRITE_EXEMPT_PATHS,
    WRITE_EXEMPT_PREFIXES,
    WRITE_EXEMPT_SUFFIXES,
    WRITE_METHODS,
)

logger = logging.getLogger(__name__)

STATE_KEY = "write_guards"


@dataclass(frozen=True)
class WriteBlock:
    """写操作被拒绝的原因；message 直接展示给用户。"""

    code: str
    message: str


WriteGuardCheck = Callable[[Any], WriteBlock | None]


def is_write_request(method: str, path: str) -> bool:
    """是否属于需要受守卫约束的写请求。"""
    if (method or "").upper() not in WRITE_METHODS:
        return False
    if path != API_PREFIX and not path.startswith(f"{API_PREFIX}/"):
        return False
    if path in WRITE_EXEMPT_PATHS or path.startswith(WRITE_EXEMPT_PREFIXES):
        return False
    return not path.endswith(WRITE_EXEMPT_SUFFIXES)


def write_guards(app: Any) -> tuple[WriteGuardCheck, ...]:
    return getattr(app.state, STATE_KEY, ())


def install_write_guards(app: Any, checks: tuple[WriteGuardCheck, ...] = ()) -> None:
    setattr(app.state, STATE_KEY, tuple(checks))


def register_write_guard(app: Any, check: WriteGuardCheck) -> None:
    """追加一个拒绝原因来源（整体替换元组，不就地修改）。"""
    setattr(app.state, STATE_KEY, (*write_guards(app), check))


def find_write_block(conn: Any) -> WriteBlock | None:
    """依次询问各来源；任一给出原因即返回，其余不再执行。"""
    for check in write_guards(conn.scope["app"]):
        try:
            block = check(conn)
        except AppError:
            raise
        except Exception:  # noqa: BLE001 - 单个检查异常不应放行也不应 500
            logger.exception("写操作守卫执行失败")
            continue
        if block is not None:
            return block
    return None


def ensure_writable(conn: Any) -> None:
    """FastAPI 依赖 / 中间件共用：写请求被拒绝时抛出 403。"""
    scope = conn.scope
    if not is_write_request(scope.get("method", ""), scope.get("path", "")):
        return
    block = find_write_block(conn)
    if block is None:
        return
    logger.info("写操作被拒绝：%s %s（%s）", scope.get("method"), scope.get("path"), block.code)
    raise AppError(block.message, status_code=403)
