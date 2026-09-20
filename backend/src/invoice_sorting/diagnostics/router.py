"""诊断接口（设计《日志与故障上报》5.1）：仅管理员可用。

- `GET /api/diagnostics/status`：是否启用上传、最近一次打包与上传结果、限流余量。
- `POST /api/diagnostics/collect`：手工生成一次诊断包，可选上传（未配置仓库时只留本机）。

这两个接口在只读降级时仍然放行（见 licensing/constants 的写操作豁免）：
服务出问题的时候恰恰最需要拿到诊断包。
"""

import logging
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from invoice_sorting.auth.deps import ADMIN_ONLY
from invoice_sorting.common.errors import AppError, ok
from invoice_sorting.diagnostics.constants import (
    DIAGNOSTICS_PREFIX,
    MSG_COLLECT_FAILED,
    REASON_CRASH,
    REASON_ERROR,
    REASON_MANUAL,
)
from invoice_sorting.diagnostics.service import (
    STATE_SERVICE_KEY,
    DiagnosticsService,
    serialize_report,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix=DIAGNOSTICS_PREFIX, tags=["诊断与上报"])


class CollectRequest(BaseModel):
    """手工生成诊断包的选项。"""

    upload: bool = False
    reason: Literal["manual", "crash", "error"] = REASON_MANUAL


def _service(request: Request) -> DiagnosticsService:
    service = getattr(request.app.state, STATE_SERVICE_KEY, None)
    if service is None:  # pragma: no cover - create_app 总会装配
        raise AppError(MSG_COLLECT_FAILED, status_code=503)
    return service


@router.get("/status", dependencies=ADMIN_ONLY)
def read_status(request: Request) -> dict[str, Any]:
    return ok(_service(request).status())


@router.post("/collect", dependencies=ADMIN_ONLY)
def collect(request: Request, body: CollectRequest | None = None) -> dict[str, Any]:
    """生成一次诊断包；upload=true 且配置了仓库与令牌时才会上传。"""
    options = body or CollectRequest()
    service = _service(request)
    try:
        report = service.collect(_reason(options.reason), upload=options.upload)
    except Exception as error:  # noqa: BLE001 - 面向用户只给中文提示，细节进日志
        logger.exception("手工生成诊断包失败")
        raise AppError(MSG_COLLECT_FAILED, status_code=500) from error
    return ok(serialize_report(report))


def _reason(value: str) -> str:
    return value if value in (REASON_MANUAL, REASON_CRASH, REASON_ERROR) else REASON_MANUAL
