"""当前操作人上下文：认证中间件校验通过后设置，业务模型据此记录上传人/操作人。

使用 ContextVar：FastAPI 同步端点与依赖在线程池中执行时会复制当前上下文，因此可见；
收件箱线程、命令行等非请求环境默认为 None。
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

_current_user_id: ContextVar[int | None] = ContextVar("current_user_id", default=None)


@dataclass(frozen=True)
class AuthUser:
    """已登录用户的快照（CurrentUser 接口形状）。"""

    id: int
    username: str
    display_name: str
    role: str

    @classmethod
    def from_model(cls, user: Any) -> "AuthUser":
        return cls(
            id=user.id, username=user.username, display_name=user.display_name, role=user.role
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
        }


def current_user_id() -> int | None:
    return _current_user_id.get()


def set_current_user(user_id: int | None) -> Token[int | None]:
    return _current_user_id.set(user_id)


def reset_current_user(token: Token[int | None]) -> None:
    _current_user_id.reset(token)


@contextmanager
def acting_as(user_id: int | None) -> Iterator[None]:
    token = set_current_user(user_id)
    try:
        yield
    finally:
        reset_current_user(token)
