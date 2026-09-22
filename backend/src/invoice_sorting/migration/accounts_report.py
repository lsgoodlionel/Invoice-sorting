"""报告里的登录账号说明（账本搬迁设计 3.1）：预览与结果共用，只给个数与用户名，不含任何哈希。

报告顶层 `accounts` 字段：`{"count": 包内账号数, "will_restore": 是否恢复, "note": 说明}`，
只在包内带账号时出现；覆盖恢复时另有 `accounts` 分区（items 中 key 为 accounts）列出每个账号的去向。
"""

from invoice_sorting.migration.report import SectionReport

SECTION_ACCOUNTS = "accounts"
LABEL_ACCOUNTS = "登录账号"

NOTE_RESTORE = (
    "同名账号的密码将恢复为备份时的密码；执行导入的管理员若在其中，导入后需用备份时的密码重新登录；"
    "本地多出的账号将被删除（执行导入的管理员本人除外）"
)
NOTE_RESTORED = (
    "登录账号已恢复为备份时的状态，本地多出的账号已删除；"
    "被改动或新建账号的登录会话已全部失效，需重新登录"
)
NOTE_MERGE = "包内含 {count} 个账号，合并模式不导入账号"
NOTE_SAAS = "包内含 {count} 个账号，SaaS 部署的账号由平台统一管理，覆盖模式不导入账号"
WARN_NO_ADMIN = "恢复后将没有可用的管理员账号（需启用中且已设置密码），执行覆盖导入时会被中止"


def accounts_info(count: int, will_restore: bool, note: str) -> dict[str, object]:
    return {"count": count, "will_restore": will_restore, "note": note}


def merge_accounts_info(count: int) -> dict[str, object] | None:
    """合并模式：一律不导入账号，包里带了就说明一句。"""
    if count <= 0:
        return None
    return accounts_info(count, will_restore=False, note=NOTE_MERGE.format(count=count))


def saas_accounts_info(count: int) -> dict[str, object] | None:
    """SaaS 目标的覆盖模式：账号是平台级的，不导入。"""
    if count <= 0:
        return None
    return accounts_info(count, will_restore=False, note=NOTE_SAAS.format(count=count))


def accounts_item(section: SectionReport) -> dict[str, object]:
    return {**section.to_dict(SECTION_ACCOUNTS), "label": LABEL_ACCOUNTS}
