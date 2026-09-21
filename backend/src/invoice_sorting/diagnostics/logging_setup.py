"""运行日志配置（设计《日志与故障上报》2 运行日志）。

- 写入 `data_dir/日志/app.log`，按大小轮转（5 MB × 5 份）。
- 根 logger 上挂一个过滤器，把密钥、令牌与密码形态的内容就地抹掉：
  即使某处代码不小心把配置整体打了出来，落盘的日志里也不会有值。
- 幂等：重复调用只会替换自己上次装的 handler，不会越加越多。
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from invoice_sorting.config import Settings
from invoice_sorting.diagnostics.constants import (
    LOG_BACKUP_COUNT,
    LOG_DATE_FORMAT,
    LOG_FORMAT,
    LOG_MAX_BYTES,
)
from invoice_sorting.diagnostics.redaction import scrub_secrets

logger = logging.getLogger(__name__)

HANDLER_MARK = "invoice_sorting_diagnostics"
DEFAULT_LEVEL = logging.INFO


class SecretFilter(logging.Filter):
    """把日志内容里的密钥形态就地替换掉；过滤器不会丢弃任何日志。"""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - 日志格式化失败不能反过来把请求搞挂
            return True
        cleaned = scrub_secrets(message)
        if cleaned != message:
            record.msg = cleaned
            record.args = ()
        return True


def resolve_level(name: str) -> int:
    """把 INVOICE_SORTING_LOG_LEVEL 解析成级别；写错了退回 INFO 而不是报错。"""
    level = logging.getLevelNamesMapping().get((name or "").strip().upper())
    return level if isinstance(level, int) else DEFAULT_LEVEL


def configure_logging(settings: Settings) -> Path | None:
    """装配根 logger 的轮转文件 handler；目录不可写时只记一条告警，不影响启动。"""
    root = logging.getLogger()
    root.setLevel(resolve_level(settings.log_level))
    _install_filter(root)
    _drop_existing(root)
    handler = _make_handler(settings.log_file)
    if handler is None:
        return None
    root.addHandler(handler)
    return settings.log_file


def _install_filter(root: logging.Logger) -> None:
    if any(isinstance(item, SecretFilter) for item in root.filters):
        return
    root.addFilter(SecretFilter())


def _drop_existing(root: logging.Logger) -> None:
    for handler in [item for item in root.handlers if getattr(item, HANDLER_MARK, False)]:
        root.removeHandler(handler)
        handler.close()


def _make_handler(path: Path) -> logging.Handler | None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8"
        )
    except OSError:
        logger.warning("无法写入运行日志文件，只保留控制台输出：%s", path)
        return None
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
    handler.addFilter(SecretFilter())
    setattr(handler, HANDLER_MARK, True)
    return handler


def log_startup_summary(settings: Settings) -> None:
    """启动摘要：只写形态与开关，**不写任何密钥或令牌**。"""
    logger.info(
        "启动：形态=%s 认证=%s 授权校验=%s 日志级别=%s 诊断上传=%s",
        settings.deployment_mode,
        settings.auth_enabled,
        settings.is_license_configured,
        settings.log_level,
        "已启用" if settings.is_log_upload_configured else "未启用",
    )
    if settings.is_smtp_env_incomplete:
        logger.warning(
            "SMTP 环境变量不完整：INVOICE_SORTING_SMTP_HOST 与 INVOICE_SORTING_SMTP_FROM "
            "只配置了一项，环境变量配置未生效，将使用网页中的邮件设置"
        )
    if settings.is_log_upload_configured:
        # 设计 8：上传属于把数据发往外部服务，启用时显著提示
        logger.warning(
            "诊断包上传已启用：故障时会把**脱敏后**的诊断包上传到私有仓库 %s（清空 "
            "INVOICE_SORTING_LOG_REPO 即可关闭）",
            settings.log_repo,
        )
