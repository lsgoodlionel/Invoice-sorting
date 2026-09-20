"""向授权服务发起校验请求。

用标准库 urllib 直连（不引入新的 HTTP 依赖）：固定超时、有限重试，失败只记日志。
区分两类结果：**服务器明确判定无效**（4xx，不重试，立即降级）与**暂时不可达**
（网络异常、5xx、429，重试后仍失败则保持宽限）。请求与日志中都不出现授权密钥。
"""

import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from invoice_sorting.licensing.constants import (
    LICENSE_VERIFY_PATH,
    MSG_SERVER_REFUSED,
    MSG_SERVER_UNREACHABLE,
)

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 10
MAX_ATTEMPTS = 3
RETRY_SLEEP_SECONDS = 1.0
MAX_RESPONSE_BYTES = 8192
MAX_ERROR_LENGTH = 120
ALLOWED_SCHEMES = ("http", "https")
# 这些状态码属于“暂时不可用”，不能当成授权无效
TRANSIENT_STATUSES = frozenset({408, 425, 429})


@dataclass(frozen=True)
class VerifyRequest:
    """上报给授权服务的信息；不包含任何业务数据。"""

    license_key: str
    instance_id: str
    app_version: str
    users: int
    tenants: int


@dataclass(frozen=True)
class VerifyOutcome:
    """一次校验的结果。token 非空表示拿到了待验签的令牌。"""

    token: str = ""
    is_reachable: bool = True
    is_rejected: bool = False
    error: str = ""


def _open(request: urllib.request.Request, timeout: float) -> Any:
    """真正发起网络请求；测试通过替换本函数保证不联网。"""
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - 协议已校验


def verify_with_server(
    server: str,
    payload: VerifyRequest,
    sleep: Callable[[float], None] = time.sleep,
) -> VerifyOutcome:
    """向授权服务校验一次；最多重试 MAX_ATTEMPTS 次。"""
    url = _build_url(server)
    if url is None:
        logger.error("授权服务地址不合法，已跳过本次校验")
        return VerifyOutcome(is_reachable=False, error=MSG_SERVER_UNREACHABLE)
    outcome = VerifyOutcome(is_reachable=False, error=MSG_SERVER_UNREACHABLE)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        outcome = _attempt(url, payload)
        if outcome.is_reachable:
            return outcome
        if attempt < MAX_ATTEMPTS:
            sleep(RETRY_SLEEP_SECONDS)
    logger.warning("授权校验失败（已重试 %s 次）：%s", MAX_ATTEMPTS, outcome.error)
    return outcome


def _build_url(server: str) -> str | None:
    parsed = urlparse((server or "").strip())
    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}{LICENSE_VERIFY_PATH}"


def _attempt(url: str, payload: VerifyRequest) -> VerifyOutcome:
    body = json.dumps(
        {
            "license_key": payload.license_key,
            "instance_id": payload.instance_id,
            "app_version": payload.app_version,
            "users": payload.users,
            "tenants": payload.tenants,
        }
    ).encode()
    request = urllib.request.Request(  # noqa: S310 - 协议已在 _build_url 校验
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with _open(request, REQUEST_TIMEOUT_SECONDS) as response:
            return _read_token(response.read(MAX_RESPONSE_BYTES))
    except urllib.error.HTTPError as error:
        return _from_http_error(error)
    except (urllib.error.URLError, OSError, ValueError) as error:
        logger.info("授权校验网络失败：%s", type(error).__name__)
        return VerifyOutcome(is_reachable=False, error=MSG_SERVER_UNREACHABLE)


def _read_token(raw: bytes) -> VerifyOutcome:
    envelope = json.loads(raw)
    token = (envelope.get("data") or {}).get("token", "")
    if not isinstance(token, str) or not token:
        raise ValueError("响应中没有令牌")
    return VerifyOutcome(token=token)


def _from_http_error(error: urllib.error.HTTPError) -> VerifyOutcome:
    """4xx（可重试的少数状态码除外）代表服务器明确判定无效。"""
    is_transient = error.code >= 500 or error.code in TRANSIENT_STATUSES
    if is_transient:
        logger.info("授权服务暂时不可用：HTTP %s", error.code)
        return VerifyOutcome(is_reachable=False, error=MSG_SERVER_UNREACHABLE)
    return VerifyOutcome(is_rejected=True, error=_error_message(error))


def _error_message(error: urllib.error.HTTPError) -> str:
    """取服务器给出的中文原因；取不到时用通用文案。"""
    try:
        envelope = json.loads(error.read(MAX_RESPONSE_BYTES))
        message = envelope.get("error")
    except (ValueError, OSError):
        message = None
    if isinstance(message, str) and message.strip():
        return message.strip()[:MAX_ERROR_LENGTH]
    return MSG_SERVER_REFUSED
