"""授权模块的路径、状态与面向用户的中文文案。

本文件不导入项目内其他模块，认证中间件可安全引用其中的公开路径常量。
"""

from importlib.metadata import PackageNotFoundError, version

PACKAGE_NAME = "invoice-sorting"
UNKNOWN_VERSION = "unknown"

LICENSE_PREFIX = "/api/license"
LICENSE_STATUS_PATH = f"{LICENSE_PREFIX}/status"
LICENSE_RECHECK_PATH = f"{LICENSE_PREFIX}/recheck"
PLATFORM_LICENSE_PREFIX = "/api/platform/license"
LICENSE_VERIFY_PATH = f"{PLATFORM_LICENSE_PREFIX}/verify"

# 注册申请的公开入口：访客没有账套，不受任何账套的只读与额度约束
SIGNUP_PREFIX = "/api/signup/"

# 只读降级时仍然放行的写请求：登录、授权自身、备份与导出、诊断包、公开注册入口
# 诊断包尤其要放行——服务出问题的时候恰恰最需要它
WRITE_EXEMPT_PREFIXES = (
    "/api/auth/",
    SIGNUP_PREFIX,
    LICENSE_PREFIX + "/",
    PLATFORM_LICENSE_PREFIX + "/",
    "/api/diagnostics/",
)
# 备份即导出（POST 登记任务）属于"把数据带走"，只读时必须仍可用；导入不在此列。
# 备份包列表与下载是 GET，本来就不受写守卫约束。
WRITE_EXEMPT_PATHS = frozenset({"/api/backup/export-tenant"})
WRITE_EXEMPT_SUFFIXES = ("/export",)
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
API_PREFIX = "/api"

BLOCK_CODE_LICENSE = "license_readonly"

MSG_ACTIVE = "授权正常。"
MSG_GRACE = "授权已过期，处于宽限期，仍可正常使用；请尽快联系供应商续期。"
MSG_READONLY_EXPIRED = (
    "授权已过期并超过宽限期，系统已切换为只读：可继续查看、导出与备份数据。"
    "请联系供应商续期；若服务器无法上网，请先恢复到授权服务的网络连接。"
)
MSG_READONLY_REVOKED = (
    "授权密钥无效或已停用，系统已切换为只读：可继续查看、导出与备份数据。请联系供应商核实后恢复。"
)
MSG_UNLICENSED_OK = "未配置授权密钥，按本机自用方式运行，不做限制。"
MSG_NOT_APPLICABLE = "多租户模式不使用私有化授权校验。"
MSG_OFFLINE_HINT = "（当前无法连接授权服务，已按离线宽限处理）"

MSG_RECHECK_TOO_OFTEN = "刚刚已经检查过，请稍后再试。"
MSG_SIGNING_UNAVAILABLE = "授权签发服务未配置，请联系管理员。"
MSG_LICENSE_REJECTED = "授权密钥无效或已停用。"
MSG_LICENSE_EXPIRED = "授权已到期，请联系供应商续期。"
MSG_LICENSE_BOUND = "该授权密钥已绑定其他实例，如需更换请联系供应商。"
MSG_SERVER_UNREACHABLE = "无法连接授权服务。"
MSG_SERVER_REFUSED = "授权服务拒绝了本次校验。"
MSG_TOKEN_INVALID = "授权服务返回的令牌无法验证。"


def app_version() -> str:
    """当前应用版本；未安装为包时返回 unknown（仅用于上报，不参与校验）。"""
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:  # pragma: no cover - 仅在非安装环境出现
        return UNKNOWN_VERSION
