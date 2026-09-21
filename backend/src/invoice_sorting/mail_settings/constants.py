"""平台邮件设置：路径、限额、校验上限与面向用户的中文文案。"""

MAIL_SETTINGS_PATH = "/mail-settings"

# 测试邮件按平台管理员限流：每分钟 3 次，防止被当作发信器
TEST_EMAIL_MAX_PER_WINDOW = 3
TEST_EMAIL_WINDOW_SECONDS = 60
# 测试连接也会让服务器去连指定主机，同样限一下频率
TEST_CONNECTION_MAX_PER_WINDOW = 10
TEST_CONNECTION_WINDOW_SECONDS = 60

HOST_MAX = 253
USERNAME_MAX = 254
PASSWORD_MAX = 256
SENDER_MAX = 320
BASE_URL_MAX = 300
PORT_MIN = 1
PORT_MAX = 65535

CHECK_CONNECTION = "connection"
CHECK_EMAIL = "email"

MSG_ENV_READONLY = "邮件由服务器环境变量配置，网页上不能修改"
MSG_NOT_CONFIGURED = "请先填写并保存 SMTP 服务器与发件人"
MSG_TOO_FREQUENT = "测试过于频繁，请 {minutes} 分钟后再试"
MSG_HOST_FORMAT = "SMTP 服务器地址格式不正确"
MSG_SENDER_FORMAT = "发件人格式不正确，应为邮箱地址或「名称 <邮箱地址>」"
MSG_BASE_URL_FORMAT = "站点地址需为 http:// 或 https:// 开头的完整地址"
MSG_NO_CONTROL_CHARS = "{label}不能包含换行等控制字符"
MSG_TOO_LONG = "{label}不能超过 {limit} 个字符"
MSG_CONNECTION_OK = "连接并登录成功"
MSG_CONNECTION_OK_NO_AUTH = "连接成功（未填写账号，未进行登录）"
MSG_EMAIL_OK = "测试邮件已发出，请到收件箱（或垃圾邮件箱）查看"

TEST_SUBJECT = "【发票报销管理】邮件设置测试"
TEST_BODY = "\n".join(
    (
        "你好：",
        "",
        "这是一封测试邮件，由平台管理员在「平台 · 邮件」页面发送，",
        "用于确认发票报销管理的邮件设置可以正常发信。",
        "",
        "收到本邮件说明配置正确，无需回复。",
    )
)

MSG_ENV_INCOMPLETE = (
    "服务器环境变量只配置了 SMTP_HOST 与 SMTP_FROM 中的一项，环境变量配置未生效，"
    "当前使用网页配置。请补全或删除这两项环境变量"
)
