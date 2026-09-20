"""命令行：`invoice-sorting diagnose [--upload] [--reason=crash|manual|error]`。

退出码（部署脚本据此判断）：

| 码 | 含义 |
| --- | --- |
| 0 | 诊断包已生成（上传成功，或本来就不上传） |
| 1 | 诊断包生成失败 |
| 2 | 诊断包已生成，但上传失败或被残留自检拦截 |

`--upload` 而未配置仓库与令牌**不是错误**：按设计默认不上传，打印提示后以 0 退出。
"""

import logging
import sys

from invoice_sorting.config import Settings
from invoice_sorting.diagnostics.constants import (
    MSG_BAD_REASON,
    MSG_COLLECT_FAILED,
    MSG_UPLOAD_DISABLED,
    REASONS,
)
from invoice_sorting.diagnostics.logging_setup import configure_logging
from invoice_sorting.diagnostics.service import DiagnosticsReport, DiagnosticsService

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_UPLOAD_FAILED = 2


def run_diagnose(settings: Settings, reason: str, upload: bool) -> None:
    """生成诊断包并按退出码表退出；任何异常都转成中文提示，不打印堆栈给使用者。"""
    if reason not in REASONS:
        _fail(MSG_BAD_REASON, EXIT_FAILED)
    configure_logging(settings)
    service = DiagnosticsService(settings)
    try:
        report = service.collect(reason, upload=upload)
    except Exception:  # noqa: BLE001 - 命令行只给一句中文提示，细节进日志
        logger.exception("生成诊断包失败")
        _fail(MSG_COLLECT_FAILED, EXIT_FAILED)
        return
    raise SystemExit(_report(report, upload, settings.is_log_upload_configured))


def _report(report: DiagnosticsReport, upload: bool, is_configured: bool) -> int:
    """打印包路径与上传结果，返回退出码。"""
    print(f"诊断包已生成：{report.package}")
    print(f"大小 {report.size} 字节，故障指纹 {report.fingerprint or '无'}")
    if report.is_truncated:
        print("日志过大，包内日志已截断保留尾部")
    if not upload:
        return EXIT_OK
    if not is_configured:
        print(MSG_UPLOAD_DISABLED)
        return EXIT_OK
    print(report.message)
    if report.is_uploaded:
        print(f"仓库内路径：{report.repo_path}")
        return EXIT_OK
    return EXIT_UPLOAD_FAILED


def _fail(message: str, code: int) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)
