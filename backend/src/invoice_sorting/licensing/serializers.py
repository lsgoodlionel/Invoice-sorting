"""授权状态的接口形状（GET /api/license/status 的 data）。"""

from typing import Any

from invoice_sorting.attachments.serializers import iso_datetime
from invoice_sorting.licensing.keys import is_test_public_key
from invoice_sorting.licensing.state import LicenseStatus


def serialize_status(status: LicenseStatus) -> dict[str, Any]:
    """字段与前端提示条一一对应；永远不包含授权密钥。

    uses_test_key：仍在用仓库内置的测试公钥（其私钥公开），运维据此知道该换密钥对了。
    """
    return {
        "uses_test_key": is_test_public_key(),
        "state": status.state,
        "message": status.message,
        "instance_id": status.instance_id,
        "valid_until": iso_datetime(status.valid_until),
        "grace_until": iso_datetime(status.grace_until),
        "max_users": status.max_users,
        "last_checked_at": iso_datetime(status.last_checked_at),
        "last_error": status.last_error,
        "server_reachable": status.server_reachable,
    }
