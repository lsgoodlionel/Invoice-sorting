"""诊断与上报测试的公共夹具。

两条硬性约束：
1. **绝不联网**：`FakeTransport` 顶替 uploader 里唯一发起请求的 `_open`。
2. **绝不出现真实令牌或用户数据**：测试里的仓库名、令牌都是明显的假值。
"""

import io
import json
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from invoice_sorting.diagnostics import system, uploader

FAKE_REPO = "example-owner/example-logs"
FAKE_TOKEN = "fake-token-for-tests-only"  # noqa: S105 - 测试用假值，非真实令牌
FIXED_TIME = datetime(2026, 9, 20, 12, 30, 0)


@dataclass
class _Call:
    method: str
    url: str
    body: dict[str, Any]
    headers: dict[str, str]


@dataclass
class FakeTransport:
    """顶替 urllib 的假传输层：按调用顺序返回预设响应，并记录请求。"""

    responses: list[Any] = field(default_factory=list)
    calls: list[_Call] = field(default_factory=list)

    def install(self, monkeypatch) -> "FakeTransport":
        monkeypatch.setattr(uploader, "_open", self._open)
        return self

    def _open(self, request, timeout):  # noqa: ANN001 - 与 urllib 签名一致
        self.calls.append(
            _Call(
                method=request.get_method(),
                url=request.full_url,
                body=json.loads(request.data.decode()) if request.data else {},
                headers={key.lower(): value for key, value in request.header_items()},
            )
        )
        outcome = self.responses.pop(0) if self.responses else _ok_response()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    @property
    def sent_paths(self) -> list[str]:
        return [call.url.split("/contents/", 1)[-1] for call in self.calls]


class _Response(io.BytesIO):
    """够用的假响应：支持 with 语句与 read(n)。"""

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _ok_response(payload: dict[str, Any] | None = None) -> _Response:
    body = payload or {"content": {"path": "invoice-sorting/logs/x", "sha": "abc"}}
    return _Response(json.dumps(body).encode())


def ok_response(payload: dict[str, Any] | None = None) -> _Response:
    return _ok_response(payload)


def http_error(code: int, message: str = "{}") -> urllib.error.HTTPError:
    """构造一个 HTTPError；body 可被 uploader 读取以取出 GitHub 的原因说明。"""
    return urllib.error.HTTPError(
        url="https://api.github.com/repos/x/y/contents/z",
        code=code,
        msg="fake",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(message.encode()),
    )


def network_error() -> urllib.error.URLError:
    return urllib.error.URLError("fake network down")


def stub_commands(monkeypatch, output: str = "（测试环境未执行外部命令）") -> None:
    """外部命令一律不真的执行，避免测试依赖 systemd、git 或网络。"""
    monkeypatch.setattr(system, "run_command", lambda args: f"{output} {args[0]}")


def package_members(path: Path) -> dict[str, str]:
    with ZipFile(path) as archive:
        return {name: archive.read(name).decode("utf-8") for name in archive.namelist()}
