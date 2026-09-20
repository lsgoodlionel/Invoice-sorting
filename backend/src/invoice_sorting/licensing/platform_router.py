"""控制面授权签发接口（无需登录，私有化实例直接调用）。

限流沿用登录失败限制器：同一来源连续提交无效密钥会被暂时锁定。
"""

from typing import Any

from fastapi import APIRouter, Request

from invoice_sorting.auth.http import client_ip
from invoice_sorting.auth.ratelimit import minutes_label
from invoice_sorting.common.errors import AppError, ok
from invoice_sorting.control.deps import ControlSessionDep
from invoice_sorting.licensing.constants import PLATFORM_LICENSE_PREFIX
from invoice_sorting.licensing.issuer import IssueRequest, issue_license_token
from invoice_sorting.licensing.schemas import LicenseVerifyRequest

router = APIRouter(prefix=PLATFORM_LICENSE_PREFIX, tags=["授权签发"])

STATE_LIMITER_KEY = "license_limiter"
MSG_TOO_MANY = "校验过于频繁，请 {minutes} 分钟后再试。"


@router.post("/verify")
def verify(
    body: LicenseVerifyRequest, request: Request, control: ControlSessionDep
) -> dict[str, Any]:
    """校验授权密钥并返回 Ed25519 签名令牌。"""
    limiter = getattr(request.app.state, STATE_LIMITER_KEY)
    key = client_ip(request)
    retry_after = limiter.retry_after(key)
    if retry_after:
        raise AppError(MSG_TOO_MANY.format(minutes=minutes_label(retry_after)), status_code=429)
    try:
        token = issue_license_token(control, _to_request(body))
    except AppError as error:
        if error.status_code < 500:  # 服务端自身未配置时不惩罚调用方
            limiter.record_failure(key)
        raise
    limiter.reset(key)
    return ok({"token": token})


def _to_request(body: LicenseVerifyRequest) -> IssueRequest:
    return IssueRequest(
        license_key=body.license_key.strip(),
        instance_id=body.instance_id.strip(),
        app_version=body.app_version,
        users=body.users,
        tenants=body.tenants,
    )
