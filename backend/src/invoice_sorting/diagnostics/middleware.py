"""故障采集中间件（纯 ASGI，设计《日志与故障上报》2 与 5.3）。

放在认证与写守卫的**内层**：这里看到的只有真正没被处理的异常和 5xx 响应，
业务层已经处理过的 4xx（用户操作反馈）不会进错误日志，避免噪音。

异常原样向上抛：本中间件只负责记录，不改变任何响应。
"""

import logging
from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from invoice_sorting.diagnostics.service import STATE_SERVICE_KEY

logger = logging.getLogger(__name__)

SERVER_ERROR_STATUS = 500


class FaultMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        status = _StatusProbe()
        try:
            await self.app(scope, receive, status.wrap(send))
        except Exception as error:
            await _on_exception(scope, error)
            raise
        if status.code >= SERVER_ERROR_STATUS:
            logger.error("请求返回 %s：%s %s", status.code, scope.get("method"), scope.get("path"))


class _StatusProbe:
    """记下响应状态码；不改动任何消息内容。"""

    def __init__(self) -> None:
        self.code = 0

    def wrap(self, send: Send) -> Send:
        async def wrapped(message: Message) -> None:
            if message["type"] == "http.response.start":
                self.code = int(message.get("status", 0))
            await send(message)

        return wrapped


async def _on_exception(scope: Scope, error: Exception) -> None:
    """记录堆栈并累计故障指纹；记录本身失败也不能掩盖原始异常。"""
    logger.exception("请求处理失败：%s %s", scope.get("method"), scope.get("path"))
    service = _service(scope)
    if service is None:
        return
    try:
        await run_in_threadpool(service.record_fault, error)
    except Exception:  # noqa: BLE001 - 诊断失败绝不能替换掉真正的异常
        logger.exception("记录故障失败")


def _service(scope: Scope) -> Any:
    app = scope.get("app")
    return getattr(app.state, STATE_SERVICE_KEY, None) if app is not None else None
