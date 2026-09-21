"""用户接口形状（docs/api-contract.md 0.2 User）。

数据取自控制面账号 + 本账套的成员关系：角色与启用状态是**账套内**的。
"""

from typing import Any

from invoice_sorting.attachments.serializers import iso_datetime
from invoice_sorting.control.members import Member


def serialize_member(member: Member) -> dict[str, Any]:
    account = member.account
    return {
        "id": account.id,
        "username": account.username,
        "display_name": account.display_name,
        "role": member.role,
        "is_active": member.is_active,
        "has_password": account.password_hash is not None,
        "created_at": iso_datetime(account.created_at),
        "last_login_at": iso_datetime(account.last_login_at),
        "source": account.source or "",  # "import"：合并导入账本时创建的停用占位账号
    }
