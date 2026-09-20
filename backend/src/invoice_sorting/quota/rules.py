"""写请求分类：这次写操作要看哪几项额度。

只有“会让用量变大”的动作才受额度约束：新建记录、上传文件、添加成员。
修改与删除永远放行，否则用户超限后连清理自救都做不到（只读降级另行判定）。
"""

from invoice_sorting.quota.constants import (
    KIND_EXPENSES,
    KIND_STORAGE,
    KIND_USERS,
    PLATFORM_PREFIX,
)

EXPENSE_PATHS = frozenset({"/api/expenses", "/api/attachments/create-expenses"})
USERS_PATH = "/api/users"
IMPORTS_PREFIX = "/api/imports"
ATTACHMENTS_SUFFIX = "/attachments"
CREATE_METHOD = "POST"


def is_quota_exempt(path: str) -> bool:
    """平台运营后台不受任何账套额度约束（要能给超限账套升级、续期、恢复）。"""
    return path.startswith(PLATFORM_PREFIX)


def checks_for(method: str, path: str) -> tuple[str, ...]:
    """该请求需要校验的额度项；返回空元组表示只受租户状态约束。"""
    if (method or "").upper() != CREATE_METHOD:
        return ()
    if path in EXPENSE_PATHS:
        return (KIND_EXPENSES,)
    if path == USERS_PATH:
        return (KIND_USERS,)
    # 导入既落文件又建记录，两项都要看
    if path == IMPORTS_PREFIX or path.startswith(f"{IMPORTS_PREFIX}/"):
        return (KIND_STORAGE, KIND_EXPENSES)
    if path.endswith(ATTACHMENTS_SUFFIX):
        return (KIND_STORAGE,)
    return ()
