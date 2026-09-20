"""故障指纹：异常类型 + 堆栈顶部位置（设计《日志与故障上报》5.3）。

指纹**不含异常消息**：消息里常带用户数据（文件名、商家名），既会泄漏也会让同一个故障
因为参数不同而算出不同指纹，限流就失效了。
"""

import hashlib
import traceback
from dataclasses import dataclass
from pathlib import Path

FINGERPRINT_LENGTH = 16
SHORT_LENGTH = 8
PACKAGE_MARKER = "invoice_sorting"
UNKNOWN_LOCATION = "unknown:0"


@dataclass(frozen=True)
class Fault:
    """一次故障的可比较标识；整体替换，不就地修改。"""

    fingerprint: str
    exc_type: str
    location: str

    @property
    def short(self) -> str:
        """包名里用的指纹前 8 位。"""
        return self.fingerprint[:SHORT_LENGTH]


def make_fingerprint(exc_type: str, location: str) -> str:
    digest = hashlib.sha256(f"{exc_type}|{location}".encode())
    return digest.hexdigest()[:FINGERPRINT_LENGTH]


def fault_from_exception(error: BaseException) -> Fault:
    """从异常对象算出指纹；取不到堆栈时退化为 unknown 位置，不抛错。"""
    exc_type = type(error).__name__
    location = _top_location(error)
    return Fault(make_fingerprint(exc_type, location), exc_type, location)


def _top_location(error: BaseException) -> str:
    """优先取**本项目**代码里最靠近抛出点的一帧，其次取最后一帧。"""
    try:
        frames = traceback.extract_tb(error.__traceback__)
    except Exception:  # noqa: BLE001 - 指纹计算不能反过来把服务搞挂
        return UNKNOWN_LOCATION
    if not frames:
        return UNKNOWN_LOCATION
    own = [frame for frame in frames if PACKAGE_MARKER in frame.filename]
    chosen = (own or frames)[-1]
    return f"{Path(chosen.filename).name}:{chosen.lineno}"
