"""待审批提醒的纯函数：通知邮箱解析与提醒正文。"""

from datetime import datetime

import pytest

from invoice_sorting.control.models import Account
from invoice_sorting.control.signup_models import SignupApplication
from invoice_sorting.db.models import TZ
from invoice_sorting.mailer.recipients import (
    NOTIFY_EMAILS_MAX,
    notify_recipients,
    split_notify_emails,
)
from invoice_sorting.signup.alerts import NEEDS_SUMMARY_MAX, pending_alert

BASE_URL = "https://fp.example.com"


def make_application(**overrides) -> SignupApplication:
    values = {
        "id": 7,
        "name": "张三",
        "email": "zhang@example.org",
        "identity": "某某大学 财务处",
        "needs": "课题组报销票据整理",
        "created_at": datetime(2026, 9, 23, 10, 30, tzinfo=TZ),
    }
    return SignupApplication(**{**values, **overrides})


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", ()),
        ("  ", ()),
        ("a@x.com", ("a@x.com",)),
        (" a@x.com , b@y.com ", ("a@x.com", "b@y.com")),
        ("a@x.com,,b@y.com", ("a@x.com", "b@y.com")),
    ],
)
def test_split_notify_emails_trims_and_drops_empties(text, expected):
    assert split_notify_emails(text) == expected


def test_notify_recipients_drops_invalid_and_caps_the_count():
    many = ",".join(f"ops{index}@example.com" for index in range(NOTIFY_EMAILS_MAX + 3))

    assert notify_recipients("ops@example.com,不是邮箱") == ("ops@example.com",)
    assert len(notify_recipients(many)) == NOTIFY_EMAILS_MAX


def test_pending_alert_lists_the_application_and_links_to_the_console():
    notice = pending_alert(make_application(), referrer=None, base_url=BASE_URL)

    assert "SQ000007" in notice.subject
    for text in ("SQ000007", "张三", "zhang@example.org", "某某大学 财务处", "2026年09月23日"):
        assert text in notice.body
    assert notice.link == f"{BASE_URL}/platform?tab=applications"
    assert notice.link in notice.body


def test_pending_alert_truncates_long_needs():
    notice = pending_alert(make_application(needs="报" * 900), referrer=None, base_url=BASE_URL)

    assert "报" * NEEDS_SUMMARY_MAX in notice.body
    assert "报" * (NEEDS_SUMMARY_MAX + 1) not in notice.body


def test_pending_alert_shows_referrer_username_and_name():
    referrer = Account(id=3, username="lisi", display_name="李四", password_hash="x")

    notice = pending_alert(make_application(), referrer=referrer, base_url=BASE_URL)

    assert "李四" in notice.body and "lisi" in notice.body


def test_pending_alert_without_base_url_gives_a_site_path():
    notice = pending_alert(make_application(), referrer=None, base_url="")

    assert notice.link == "/platform?tab=applications"
