"""发给平台通知邮箱的「有新申请待审批」提醒（中文）。

收件人是平台管理员，所以可以写明申请人资料与推荐人，便于直接判断；
但**不含注册码、注册链接、密码或任何凭据**——这些只发给申请人本人。
需求简介可能很长，截断到 NEEDS_SUMMARY_MAX 个字符，完整内容去后台看。
"""

from invoice_sorting.control.models import Account
from invoice_sorting.control.signup_models import SignupApplication
from invoice_sorting.signup.codes import application_number
from invoice_sorting.signup.notices import PRODUCT_NAME, Notice, site_link

PLATFORM_PATH = "/platform?tab=applications"
NEEDS_SUMMARY_MAX = 200
ELLIPSIS = "…"
SUBMITTED_FORMAT = "%Y年%m月%d日 %H:%M"
SUBJECT_FORMAT = f"【{PRODUCT_NAME}】有新的注册申请待审批（{{number}}）"


def console_link(base_url: str) -> str:
    """平台后台申请列表的直达地址；没有站点地址时给站内路径。"""
    return site_link(base_url, PLATFORM_PATH)


def needs_summary(needs: str) -> str:
    text = (needs or "").strip()
    return text if len(text) <= NEEDS_SUMMARY_MAX else text[:NEEDS_SUMMARY_MAX] + ELLIPSIS


def referrer_label(referrer: Account | None) -> str:
    if referrer is None:
        return ""
    return f"{referrer.display_name or referrer.username}（{referrer.username}）"


def _submitted_at(application: SignupApplication) -> str:
    created = application.created_at
    return created.strftime(SUBMITTED_FORMAT) if created is not None else ""


def _lines(application: SignupApplication, referrer: Account | None, link: str) -> list[str]:
    label = referrer_label(referrer)
    lines = [
        "平台管理员：",
        "",
        "有一条新的注册申请等待审批。",
        "",
        f"申请编号：{application_number(application.id)}",
        f"姓名：{application.name}",
        f"邮箱：{application.email}",
        f"单位或身份：{application.identity}",
    ]
    if label:
        lines.append(f"推荐人：{label}")
    lines.extend(
        (
            f"提交时间：{_submitted_at(application)}",
            f"需求简介：{needs_summary(application.needs)}",
            "",
            "去后台处理：",
            link,
            "",
            "本邮件由系统自动发送，请勿回复。",
        )
    )
    return lines


def pending_alert(
    application: SignupApplication, referrer: Account | None, base_url: str
) -> Notice:
    link = console_link(base_url)
    subject = SUBJECT_FORMAT.format(number=application_number(application.id))
    return Notice(subject=subject, body="\n".join(_lines(application, referrer, link)), link=link)
