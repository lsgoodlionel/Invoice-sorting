"""写请求分类：哪种写操作要看哪一项额度，哪些路径完全不受额度约束。"""

import pytest

from invoice_sorting.quota.constants import KIND_EXPENSES, KIND_STORAGE, KIND_USERS
from invoice_sorting.quota.rules import checks_for, is_quota_exempt


@pytest.mark.parametrize(
    ("method", "path", "expected"),
    [
        ("POST", "/api/expenses", (KIND_EXPENSES,)),
        ("POST", "/api/attachments/create-expenses", (KIND_EXPENSES,)),
        ("POST", "/api/expenses/7/attachments", (KIND_STORAGE,)),
        ("POST", "/api/imports", (KIND_STORAGE, KIND_EXPENSES)),
        ("POST", "/api/imports/abc/files", (KIND_STORAGE, KIND_EXPENSES)),
        ("POST", "/api/users", (KIND_USERS,)),
        ("PATCH", "/api/expenses/7", ()),
        ("DELETE", "/api/expenses/7", ()),
        ("PATCH", "/api/users/3", ()),
        ("PUT", "/api/settings", ()),
        ("POST", "/api/invites", ()),
    ],
)
def test_checks_for_maps_paths_to_quota_items(method, path, expected):
    assert checks_for(method, path) == expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/platform/tenants", True),
        ("/api/platform/license/verify", True),
        ("/api/expenses", False),
    ],
)
def test_platform_backoffice_is_never_blocked_by_tenant_quota(path, expected):
    """运营后台要能对停用/超限的账套改套餐、延期、恢复，不能被目标账套的状态挡住。"""
    assert is_quota_exempt(path) is expected
