"""UserRef：上传人/操作人展示（docs/api-contract.md 0.3）。不依赖其他序列化模块，避免循环导入。"""

from typing import Any

from invoice_sorting.db.models import User


def user_ref(user: User | None) -> dict[str, Any] | None:
    """已停用用户仍返回姓名；收件箱、关闭认证等无操作人时为 None。"""
    if user is None:
        return None
    return {"id": user.id, "display_name": user.display_name}
