"""诊断与上报的编排（设计《日志与故障上报》5 触发方式、6 上传）。

对外只有三个入口，全部**兜住异常**：诊断本身出问题绝不能影响正在排查的服务。

- `record_fault`：运行中出错时累计指纹，够阈值且未被限流就在后台打一次包；
- `collect`：手工（命令行或接口）生成一次，不受限流影响；
- `status`：是否启用上传、最近一次结果、限流余量。
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from invoice_sorting.config import Settings
from invoice_sorting.db.models import now
from invoice_sorting.diagnostics import uploader
from invoice_sorting.diagnostics.collect import DiagnosticPackage, collect_package
from invoice_sorting.diagnostics.constants import (
    MSG_COLLECT_FAILED,
    MSG_RESIDUE_BLOCKED,
    MSG_UPLOAD_DISABLED,
    MSG_UPLOAD_FAILED,
    MSG_UPLOAD_OK,
    REASON_ERROR,
    REASON_MANUAL,
)
from invoice_sorting.diagnostics.fingerprint import Fault, fault_from_exception
from invoice_sorting.diagnostics.system import host_short_name
from invoice_sorting.diagnostics.tracker import FaultTracker, state_path
from invoice_sorting.licensing.constants import app_version

logger = logging.getLogger(__name__)

STATE_SERVICE_KEY = "diagnostics"
Runner = Callable[[Callable[[], None]], None]


@dataclass(frozen=True)
class DiagnosticsReport:
    """最近一次打包与上传的结果；整体替换，不就地修改。"""

    created_at: datetime
    reason: str
    fingerprint: str
    package: Path
    size: int
    residue: tuple[str, ...] = ()
    is_truncated: bool = False
    is_uploaded: bool = False
    repo_path: str = ""
    message: str = ""


def _spawn(job: Callable[[], None]) -> None:
    """后台线程执行，绝不阻塞请求或崩溃处理流程。"""
    threading.Thread(target=job, name="diagnostics", daemon=True).start()


class DiagnosticsService:
    def __init__(
        self,
        settings: Settings,
        health_provider: Callable[[], dict[str, Any]] | None = None,
        runner: Runner = _spawn,
        clock: Callable[[], datetime] = now,
    ) -> None:
        self._settings = settings
        self._health_provider = health_provider
        self._runner = runner
        self._clock = clock
        self._tracker = FaultTracker(state_path(settings.logs_dir))
        self._busy = threading.Lock()
        self._last: DiagnosticsReport | None = None

    @property
    def is_upload_enabled(self) -> bool:
        return self._settings.is_log_upload_configured

    @property
    def last_report(self) -> DiagnosticsReport | None:
        return self._last

    def record_fault(self, error: BaseException) -> Fault:
        """累计一次故障；够阈值且未被限流时在后台生成（并按配置上传）诊断包。"""
        fault = fault_from_exception(error)
        try:
            decision = self._tracker.record(fault.fingerprint, self._clock())
        except Exception:  # noqa: BLE001 - 限流失败不影响主流程
            logger.exception("记录故障指纹失败")
            return fault
        logger.info(
            "故障指纹 %s（%s @ %s）窗口内第 %s 次：%s",
            fault.short,
            fault.exc_type,
            fault.location,
            decision.hits,
            decision.reason,
        )
        if decision.should_collect:
            self._runner(lambda: self.collect_safely(REASON_ERROR, upload=True, fault=fault))
        return fault

    def collect_safely(
        self, reason: str, upload: bool, fault: Fault | None = None
    ) -> DiagnosticsReport | None:
        """后台入口：任何异常只记日志，不向上传播。"""
        try:
            return self.collect(reason, upload=upload, fault=fault)
        except Exception:  # noqa: BLE001 - 诊断失败绝不能影响主流程
            logger.exception("生成诊断包失败（%s）", reason)
            return None

    def collect(
        self, reason: str = REASON_MANUAL, upload: bool = False, fault: Fault | None = None
    ) -> DiagnosticsReport:
        """生成一次诊断包；同一时间只允许一个在跑，崩溃风暴不会堆出一堆线程。"""
        if not self._busy.acquire(blocking=False):
            raise RuntimeError(MSG_COLLECT_FAILED)
        try:
            package = collect_package(
                self._settings, reason, self._clock(), fault=fault, health=self._health()
            )
            report = _to_report(package)
            self._last = self._deliver(report, package) if upload else report
            return self._last
        finally:
            self._busy.release()

    def _health(self) -> dict[str, Any] | None:
        try:
            return self._health_provider() if self._health_provider is not None else None
        except Exception:  # noqa: BLE001 - 取不到健康信息也要出包
            logger.exception("采集健康状态失败，诊断包中留空")
            return None

    def _deliver(self, report: DiagnosticsReport, package: DiagnosticPackage) -> DiagnosticsReport:
        """脱敏自检通过 + 配置齐备才上传；否则只保留本地包并说明原因。"""
        if not package.is_safe_to_upload:
            message = MSG_RESIDUE_BLOCKED.format(types="、".join(package.residue))
            logger.error("%s 包：%s", message, package.path.name)
            return replace(report, message=message)
        target = uploader.build_target(self._settings, host_short_name())
        if target is None:
            return replace(report, message=MSG_UPLOAD_DISABLED)
        return self._upload(report, package, target)

    def _upload(
        self,
        report: DiagnosticsReport,
        package: DiagnosticPackage,
        target: uploader.UploadTarget,
    ) -> DiagnosticsReport:
        message = _commit_message(package)
        outcome = uploader.upload_package(target, package.path, package.created_at, message)
        if not outcome.is_uploaded:
            logger.warning("%s 原因：%s", MSG_UPLOAD_FAILED, outcome.error)
            return replace(report, message=f"{MSG_UPLOAD_FAILED}（{outcome.error}）")
        logger.info("诊断包已上传：%s/%s", target.repo, outcome.repo_path)
        uploader.update_latest(target, _latest_payload(target, package, outcome.repo_path), message)
        return replace(report, is_uploaded=True, repo_path=outcome.repo_path, message=MSG_UPLOAD_OK)

    def status(self) -> dict[str, Any]:
        """管理员接口用：是否启用上传、最近一次结果、限流余量。"""
        state = self._tracker.snapshot()
        return {
            "upload_enabled": self.is_upload_enabled,
            "repo": self._settings.log_repo if self.is_upload_enabled else "",
            "app": self._settings.log_app,
            "instance": self._settings.log_instance or host_short_name(),
            "log_file": str(self._settings.log_file),
            "last": serialize_report(self._last),
            "throttle": {
                "daily_used": state.daily_count,
                "daily_remaining": state.remaining_today(),
                "tracked_fingerprints": len(state.occurrences),
            },
        }


def _to_report(package: DiagnosticPackage) -> DiagnosticsReport:
    return DiagnosticsReport(
        created_at=package.created_at,
        reason=package.reason,
        fingerprint=package.fingerprint,
        package=package.path,
        size=package.size,
        residue=package.residue,
        is_truncated=package.is_truncated,
    )


def _commit_message(package: DiagnosticPackage) -> str:
    """提交说明只含指纹与版本，不含任何业务数据。"""
    return f"[invoice-sorting] {package.reason} {package.fingerprint or 'nofp'} v{app_version()}"


def _latest_payload(
    target: uploader.UploadTarget, package: DiagnosticPackage, repo_path: str
) -> dict[str, Any]:
    return {
        "app": target.app,
        "instance": target.instance,
        "reason": package.reason,
        "fingerprint": package.fingerprint,
        "version": app_version(),
        "time": package.created_at.isoformat(),
        "package": repo_path,
    }


def serialize_report(report: DiagnosticsReport | None) -> dict[str, Any] | None:
    if report is None:
        return None
    return {
        "created_at": report.created_at.isoformat(),
        "reason": report.reason,
        "fingerprint": report.fingerprint,
        "package": report.package.name,
        "size": report.size,
        "residue": list(report.residue),
        "is_truncated": report.is_truncated,
        "is_uploaded": report.is_uploaded,
        "repo_path": report.repo_path,
        "message": report.message,
    }
