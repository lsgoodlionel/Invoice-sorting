"""额度模块的路径、标识与面向用户的中文文案。

本文件不导入项目内其他模块，任何地方都可以安全引用其中的常量。
文案要求：说清楚**超的是哪一项**、上限多少、当前多少、以及用户能做什么。
"""

QUOTA_PATH = "/api/quota"
# 平台运营后台：要能给停用/超限的账套改套餐、延期与恢复，不受目标账套状态影响
PLATFORM_PREFIX = "/api/platform/"

KIND_USERS = "users"
KIND_STORAGE = "storage"
KIND_EXPENSES = "expenses"
KINDS = (KIND_USERS, KIND_STORAGE, KIND_EXPENSES)

LABELS = {
    KIND_USERS: "成员数量",
    KIND_STORAGE: "存储空间",
    KIND_EXPENSES: "本月新增记录",
}
UNITS = {KIND_USERS: "人", KIND_STORAGE: "MB", KIND_EXPENSES: "条"}

BLOCK_CODE_READONLY = "tenant_readonly"
BLOCK_CODE_QUOTA = "quota_exceeded"

REASON_SUSPENDED = "tenant_suspended"
REASON_CLOSED = "tenant_closed"
REASON_EXPIRED = "tenant_expired"

_READONLY_TAIL = "系统当前为只读：可以继续查看、导出与备份数据，但不能新增与修改。"

MSG_SUSPENDED = f"账套已停用，{_READONLY_TAIL}请联系平台管理员恢复后再操作。"
MSG_CLOSED = f"账套已关闭，{_READONLY_TAIL}如需继续使用请联系平台管理员。"
MSG_EXPIRED = "订阅已到期（{day}），" + _READONLY_TAIL + "请联系平台管理员续期后恢复。"

MSG_EXCEEDED = {
    KIND_USERS: (
        "成员数量已达套餐上限（{plan}：最多 {limit} 人，当前 {used} 人），无法再添加成员。"
        "请升级套餐，或停用不再使用的成员后重试。"
    ),
    KIND_STORAGE: (
        "存储空间已达套餐上限（{plan}：最多 {limit} MB，当前约 {used} MB），无法再上传文件。"
        "请升级套餐，或清理不再需要的附件后重试。"
    ),
    KIND_EXPENSES: (
        "本月新增记录已达套餐上限（{plan}：每月 {limit} 条，本月已新增 {used} 条），"
        "无法再新建记录。请升级套餐，或等下月额度重置。"
    ),
}
