"""把诊断包上传到**私有**日志仓库（设计《日志与故障上报》6 上传）。

- 用标准库 urllib 直连 GitHub Contents API，不引入新依赖；测试替换 `_open` 保证不联网。
- 令牌只从 Settings（即环境变量）取，只出现在 Authorization 请求头里：
  不落库、不写日志、不进诊断包，错误信息回传前还会再过一遍脱敏。
- 代码中**没有默认仓库兜底**：`build_target` 在配置缺失时返回 None，调用方据此跳过上传。
- 仓库尚无任何提交时，带 branch 的 PUT 会被拒绝；此时去掉 branch 重试一次，
  由 GitHub 创建默认分支与首个文件。
"""

import base64
import json
import logging
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from invoice_sorting.config import Settings
from invoice_sorting.diagnostics.constants import (
    GITHUB_API_ROOT,
    GITHUB_API_VERSION,
    LATEST_FILENAME,
    LOGS_SEGMENT,
    MAX_PACKAGE_BYTES,
    UPLOAD_MAX_ATTEMPTS,
    UPLOAD_RETRY_SLEEP_SECONDS,
    UPLOAD_TIMEOUT_SECONDS,
)
from invoice_sorting.diagnostics.redaction import redact_text

logger = logging.getLogger(__name__)

REPO_PATTERN = re.compile(r"^[A-Za-z0-9._\-]+/[A-Za-z0-9._\-]+$")
SEGMENT_PATTERN = re.compile(r"[^A-Za-z0-9._\-]+")
MAX_RESPONSE_BYTES = 16384
MAX_ERROR_LENGTH = 200
DATE_FORMAT = "%Y-%m-%d"
# 这些状态码说明“分支还不存在”（空仓库首次上传），去掉 branch 再试一次
EMPTY_REPO_STATUSES = frozenset({404, 409, 422})
TRANSIENT_STATUSES = frozenset({408, 425, 429})

MSG_NOT_CONFIGURED = "未配置日志仓库或令牌"
MSG_BAD_REPO = "日志仓库格式应为 owner/repo"
MSG_UNREACHABLE = "无法连接日志仓库"
MSG_REFUSED = "日志仓库拒绝了本次上传"
MSG_TOO_LARGE = "诊断包超过上传体积上限"


@dataclass(frozen=True)
class UploadTarget:
    """一次上传的目标；token 只在内存中流转。"""

    repo: str
    token: str
    app: str
    instance: str
    branch: str


@dataclass(frozen=True)
class UploadOutcome:
    """上传结果；error 已脱敏，可以安全写进日志与接口响应。"""

    is_uploaded: bool
    repo_path: str = ""
    error: str = ""
    is_branch_missing: bool = False


def build_target(settings: Settings, instance: str) -> UploadTarget | None:
    """配置齐备且仓库格式合法时返回目标，否则返回 None（不上传）。"""
    if not settings.is_log_upload_configured:
        return None
    repo = settings.log_repo.strip()
    if REPO_PATTERN.match(repo) is None:
        logger.error("日志仓库格式不合法，已跳过上传（应为 owner/repo）")
        return None
    return UploadTarget(
        repo=repo,
        token=settings.log_token.strip(),
        app=_segment(settings.log_app),
        instance=_segment(settings.log_instance or instance),
        branch=settings.log_branch.strip(),
    )


def _segment(value: str) -> str:
    """路径片段只允许安全字符，避免配置值穿越到别的应用命名空间。"""
    return SEGMENT_PATTERN.sub("-", (value or "").strip()).strip("-.") or "unknown"


def package_repo_path(target: UploadTarget, created_at: Any, filename: str) -> str:
    """`<应用>/logs/<实例名>/<日期>/<包名>`；仓库由多个应用共用，先按应用分命名空间。"""
    day = created_at.strftime(DATE_FORMAT)
    return f"{target.app}/{LOGS_SEGMENT}/{target.instance}/{day}/{_segment(filename)}"


def latest_repo_path(target: UploadTarget) -> str:
    return f"{target.app}/{LATEST_FILENAME}"


def _open(request: urllib.request.Request, timeout: float) -> Any:
    """真正发起网络请求；测试替换本函数保证不联网。"""
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310 - 固定 https 域名


def put_file(
    target: UploadTarget,
    repo_path: str,
    content: bytes,
    message: str,
    sleep: Callable[[float], None] = time.sleep,
    overwrite: bool = False,
) -> UploadOutcome:
    """写入仓库中的一个文件；空仓库首次写入会自动创建默认分支。

    `overwrite=True` 时先查一次现有 sha（覆盖 latest.json 必须带 sha）；
    诊断包路径含时间戳，不会重名，省掉这次请求。
    """
    if len(content) > MAX_PACKAGE_BYTES:
        return UploadOutcome(False, error=MSG_TOO_LARGE)
    payload = {
        "message": message,
        "content": base64.b64encode(content).decode(),
        **({"branch": target.branch} if target.branch else {}),
    }
    sha = _existing_sha(target, repo_path) if overwrite else ""
    if sha:
        payload = {**payload, "sha": sha}
    outcome = _put_with_retry(target, repo_path, payload, sleep)
    if outcome.is_uploaded or not target.branch or not outcome.is_branch_missing:
        return outcome
    retry = {key: value for key, value in payload.items() if key != "branch"}
    logger.info("日志仓库尚无提交，改用默认分支重试一次")
    return _put_with_retry(target, repo_path, retry, sleep)


def _put_with_retry(
    target: UploadTarget, repo_path: str, payload: dict[str, Any], sleep: Callable[[float], None]
) -> UploadOutcome:
    outcome = UploadOutcome(False, error=MSG_UNREACHABLE)
    for attempt in range(1, UPLOAD_MAX_ATTEMPTS + 1):
        outcome = _attempt_put(target, repo_path, payload)
        if outcome.is_uploaded or not _is_retriable(outcome):
            return outcome
        if attempt < UPLOAD_MAX_ATTEMPTS:
            sleep(UPLOAD_RETRY_SLEEP_SECONDS)
    return outcome


def _is_retriable(outcome: UploadOutcome) -> bool:
    return outcome.error == MSG_UNREACHABLE


def _attempt_put(target: UploadTarget, repo_path: str, payload: dict[str, Any]) -> UploadOutcome:
    request = _build_request(target, repo_path, method="PUT", payload=payload)
    try:
        with _open(request, UPLOAD_TIMEOUT_SECONDS) as response:
            response.read(MAX_RESPONSE_BYTES)
        return UploadOutcome(True, repo_path=repo_path)
    except urllib.error.HTTPError as error:
        return _from_http_error(error, target)
    except (urllib.error.URLError, OSError, ValueError) as error:
        logger.info("上传诊断包网络失败：%s", type(error).__name__)
        return UploadOutcome(False, error=MSG_UNREACHABLE)


def _existing_sha(target: UploadTarget, repo_path: str) -> str:
    """覆盖已有文件必须带 sha；文件不存在或仓库为空时返回空串。"""
    request = _build_request(target, repo_path, method="GET")
    try:
        with _open(request, UPLOAD_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read(MAX_RESPONSE_BYTES))
    except (urllib.error.URLError, OSError, ValueError):
        return ""
    sha = body.get("sha") if isinstance(body, dict) else None
    return sha if isinstance(sha, str) else ""


def _build_request(
    target: UploadTarget, repo_path: str, method: str, payload: dict[str, Any] | None = None
) -> urllib.request.Request:
    url = f"{GITHUB_API_ROOT}/repos/{target.repo}/contents/{repo_path}"
    headers = {
        "Authorization": f"Bearer {target.token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
        "User-Agent": "invoice-sorting-diagnostics",
    }
    data = json.dumps(payload).encode() if payload is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    return urllib.request.Request(url, data=data, headers=headers, method=method)  # noqa: S310 - 固定 https 域名


def _from_http_error(error: urllib.error.HTTPError, target: UploadTarget) -> UploadOutcome:
    if error.code >= 500 or error.code in TRANSIENT_STATUSES:
        logger.info("日志仓库暂时不可用：HTTP %s", error.code)
        return UploadOutcome(False, error=MSG_UNREACHABLE)
    detail = _safe_error(error, target.token)
    return UploadOutcome(
        False,
        error=f"{MSG_REFUSED}（HTTP {error.code}：{detail}）",
        is_branch_missing=error.code in EMPTY_REPO_STATUSES,
    )


def _safe_error(error: urllib.error.HTTPError, token: str) -> str:
    """取 GitHub 的原因说明，去掉可能带上的令牌，再整体脱敏后截断。"""
    try:
        body = json.loads(error.read(MAX_RESPONSE_BYTES))
        message = body.get("message") if isinstance(body, dict) else None
    except (ValueError, OSError):
        message = None
    text = message if isinstance(message, str) and message.strip() else MSG_REFUSED
    if token:
        text = text.replace(token, "<已隐去>")
    return redact_text(text)[:MAX_ERROR_LENGTH]


def upload_package(
    target: UploadTarget,
    package_path: Any,
    created_at: Any,
    message: str,
    sleep: Callable[[float], None] = time.sleep,
) -> UploadOutcome:
    """把诊断包 zip 上传到 `<应用>/logs/<实例名>/<日期>/<包名>`。"""
    repo_path = package_repo_path(target, created_at, package_path.name)
    try:
        content = package_path.read_bytes()
    except OSError:
        return UploadOutcome(False, error="诊断包已不可读")
    return put_file(target, repo_path, content, message, sleep)


def update_latest(
    target: UploadTarget,
    payload: dict[str, Any],
    message: str,
    sleep: Callable[[float], None] = time.sleep,
) -> UploadOutcome:
    """维护 `<应用>/latest.json`：最近一次故障的指纹、版本、时间与包路径。"""
    content = json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode()
    return put_file(target, latest_repo_path(target), content, message, sleep, overwrite=True)
