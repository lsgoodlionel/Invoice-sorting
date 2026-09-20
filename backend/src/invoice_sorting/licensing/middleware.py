"""写操作守卫中间件（纯 ASGI）：只读降级时拦截写请求。

放在认证中间件**内层**，这样未登录的写请求先得到 401，不会泄漏本机授权状态。
只处理写方法的 /api 请求，其余（含 GET、登录、导出、备份）直接放行。
"""

from starlette.concurrency import run_in_threadpool
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from invoice_sorting.common.errors import AppError
from invoice_sorting.licensing.guard import ensure_writable, is_write_request


class WriteGuardMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not is_write_request(scope["method"], scope["path"]):
            await self.app(scope, receive, send)
            return
        try:
            # 放到线程池执行：后续批次的额度检查可能要读数据库
            await run_in_threadpool(ensure_writable, HTTPConnection(scope))
        except AppError as error:
            response = JSONResponse(
                {"ok": False, "data": None, "error": error.message}, status_code=error.status_code
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
