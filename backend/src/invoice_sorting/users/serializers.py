"""用户接口形状（docs/api-contract.md 0.2 User）。"""

from typing import Any

from invoice_sorting.attachments.serializers import iso_datetime
from invoice_sorting.db.models import User


def serialize_user(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": bool(user.is_active),
        "has_password": user.password_hash is not None,
        "created_at": iso_datetime(user.created_at),
        "last_login_at": iso_datetime(user.last_login_at),
    }
