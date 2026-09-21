"""审批结果通知：邮件模板（中文）与“未配置 SMTP 时由管理员转告”的同一段文字。

邮件只含结果、注册链接与有效期，**不含密码、推荐人或任何账本数据**。
"""

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

from invoice_sorting.signup.constants import APPLY_PATH, REGISTER_PATH

PRODUCT_NAME = "发票报销管理"
SUBJECT_APPROVED = f"【{PRODUCT_NAME}】你的使用申请已通过"
SUBJECT_REJECTED = f"【{PRODUCT_NAME}】你的使用申请未通过"
EXPIRES_FORMAT = "%Y年%m月%d日 %H:%M"


@dataclass(frozen=True)
class Notice:
    """一封通知：link 仅批准类通知才有。"""

    subject: str
    body: str
    link: str = ""


def site_link(base_url: str, path: str) -> str:
    """配置了 PUBLIC_BASE_URL 时给出完整地址，否则给出站内路径（前端自行补全域名）。"""
    return f"{(base_url or '').strip().rstrip('/')}{path}"


def register_link(base_url: str, code: str) -> str:
    return site_link(base_url, f"{REGISTER_PATH}?code={quote(code, safe='')}")


def referral_link(base_url: str, code: str) -> str:
    return site_link(base_url, f"{APPLY_PATH}?ref={quote(code, safe='')}")


def approved_notice(name: str, link: str, expires_at: datetime) -> Notice:
    body = "\n".join(
        (
            f"{name or '你好'}：",
            "",
            f"你提交的「{PRODUCT_NAME}」使用申请已通过。",
            "请打开下面的注册链接，设置用户名与密码即可开通你的独立账本：",
            "",
            link,
            "",
            f"链接有效期至 {expires_at.strftime(EXPIRES_FORMAT)}，只能使用一次。",
            "如果不是你本人提交的申请，请忽略本邮件。",
        )
    )
    return Notice(subject=SUBJECT_APPROVED, body=body, link=link)


def rejected_notice(name: str, reason: str) -> Notice:
    lines = [
        f"{name or '你好'}：",
        "",
        f"很抱歉，你提交的「{PRODUCT_NAME}」使用申请未通过。",
    ]
    if reason:
        lines.append(f"原因：{reason}")
    lines.extend(("", "如有疑问，可以补充说明后重新提交申请。"))
    return Notice(subject=SUBJECT_REJECTED, body="\n".join(lines))
