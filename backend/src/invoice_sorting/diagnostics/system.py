"""向系统取信息：执行外部命令、读文件尾部、读主机名（设计《日志与故障上报》3）。

所有函数都**不抛异常**：诊断包尽力而为，取不到的部分写明原因即可，绝不能反过来
把正在排查的服务再搞挂一次。测试通过替换 `run_command` 保证不真的执行 systemctl。
"""

import logging
import os
import socket
import subprocess
from pathlib import Path

from invoice_sorting.diagnostics.constants import COMMAND_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

MAX_TAIL_BYTES = 2 * 1024 * 1024
MSG_COMMAND_MISSING = "（命令不可用：{name}）"
MSG_COMMAND_FAILED = "（命令执行失败：{name}）"
MSG_FILE_MISSING = "（文件不存在或不可读：{path}）"


def run_command(args: tuple[str, ...]) -> str:
    """执行只读诊断命令；命令不存在、超时或失败都返回一句中文说明。"""
    try:
        completed = subprocess.run(  # noqa: S603 - 参数为代码内固定的只读命令
            list(args),
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        return MSG_COMMAND_MISSING.format(name=args[0])
    except (OSError, subprocess.SubprocessError):
        logger.info("诊断命令执行失败：%s", args[0])
        return MSG_COMMAND_FAILED.format(name=args[0])
    output = (completed.stdout or "") + (completed.stderr or "")
    return output.strip() or MSG_COMMAND_FAILED.format(name=args[0])


def read_tail(path: Path, lines: int) -> str:
    """读文件末尾若干行；文件很大时只从尾部读固定字节，不整体载入。"""
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > MAX_TAIL_BYTES:
                handle.seek(size - MAX_TAIL_BYTES)
            raw = handle.read()
    except OSError:
        return MSG_FILE_MISSING.format(path=path.name)
    text = raw.decode("utf-8", errors="replace")
    return "\n".join(text.splitlines()[-lines:])


def host_short_name() -> str:
    """主机短名；取不到时退化为 unknown（不进一步暴露网络信息）。"""
    try:
        return socket.gethostname().split(".")[0] or "unknown"
    except OSError:  # pragma: no cover - 正常系统不会失败
        return "unknown"


def env_presence(names: tuple[str, ...], set_label: str, unset_label: str) -> str:
    """只写变量名与是否设置；**任何情况下都不写值**。

    刻意不用 `名=值` 的形态：脱敏规则会把密钥类键名后面的内容一律隐去，
    连“已设置/未设置”这个结论也会被抹掉，反而看不出配没配。
    """
    rows = (f"{name}  {set_label if os.environ.get(name) else unset_label}" for name in names)
    return "\n".join(rows)
