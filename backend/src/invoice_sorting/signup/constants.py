"""注册申请与推荐：路径、限额与面向用户的中文文案。"""

SIGNUP_API = "/api/signup"
REFERRALS_API = "/api/referrals"

# 申请接口按 IP 限流：每小时 5 次（设计 5）
APPLY_MAX_PER_WINDOW = 5
APPLY_WINDOW_SECONDS = 60 * 60
# 推荐码与注册码校验按 IP 统计失败次数，防止穷举
CODE_MAX_FAILURES = 10
CODE_WINDOW_SECONDS = 15 * 60

PURGE_AFTER_DAYS = 180
CODE_VALID_DAYS_MIN = 1
CODE_VALID_DAYS_MAX = 30
REFERRAL_QUOTA_MAX = 1000

NAME_MAX = 32
EMAIL_MAX = 254
IDENTITY_MAX = 100
NEEDS_MAX = 1000
LEDGER_NAME_MAX = 100
REASON_MAX = 200
HONEYPOT_MAX = 200
REFERRAL_CODE_MAX = 32
REGISTER_CODE_MAX = 128
SEARCH_MAX = 50

REGISTER_PATH = "/register"
APPLY_PATH = "/apply"

MSG_SAAS_ONLY = "当前部署未开放注册申请"
MSG_TOO_FREQUENT = "提交过于频繁，请 {minutes} 分钟后再试"
MSG_DUPLICATE_PENDING = "该邮箱已有待审批的申请，请耐心等待审批结果"
MSG_REFERRAL_INVALID = "推荐链接无效或已失效"
MSG_REFERRAL_DISABLED = "你的推荐资格已被停用，如有疑问请联系平台"
MSG_CODE_INVALID = "注册链接无效，请核对邮件中的链接"
MSG_CODE_USED = "该注册链接已使用过，请直接登录"
MSG_CODE_EXPIRED = "注册链接已过期，请联系平台重新发送"
MSG_EMAIL_MISMATCH = "邮箱与申请时填写的不一致"
MSG_NOT_PENDING = "该申请已处理，不能重复审批"
MSG_RESEND_NOT_ALLOWED = "只有已批准待注册或已否决的申请可以重新发送"
MSG_RESEND_PURGED = "该申请的资料已按规定清除，无法重新发送"
MSG_SLUG_RESERVED = "账套标识已被其他已批准的申请占用"
MSG_LOGIN_REQUIRED = "请先登录"
MSG_EMAIL_FORMAT = "邮箱格式不正确"
MSG_SUBMITTED = "申请已提交，审批结果会发到你的邮箱"
MSG_SUBMITTED_DIRECT = "注册链接已发送到你的邮箱，请在有效期内完成注册"

WHAT_APPLICATION = "申请"
WHAT_ACCOUNT = "账号"
