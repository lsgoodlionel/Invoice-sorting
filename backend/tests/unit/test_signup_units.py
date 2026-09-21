"""注册申请的纯函数与后台任务：码与哈希、邮箱脱敏、链接、通知模板、清理线程自愈。"""

from datetime import datetime

from invoice_sorting.db.models import TZ
from invoice_sorting.signup.codes import (
    REFERRAL_ALPHABET,
    hash_code,
    hash_ip,
    is_valid_email,
    mask_email,
    new_referral_code,
    new_register_code,
)
from invoice_sorting.signup.notices import approved_notice, referral_link, register_link
from invoice_sorting.signup.scheduler import DailyTask


def test_register_code_is_random_and_hash_is_sha256():
    first, second = new_register_code(), new_register_code()

    assert first != second and len(first) >= 32
    assert len(hash_code(first)) == 64 and hash_code(f" {first} ") == hash_code(first)


def test_referral_code_avoids_confusing_characters():
    code = new_referral_code()

    assert len(code) == 8 and set(code) <= set(REFERRAL_ALPHABET)
    assert not set("IO01") & set(code)


def test_ip_hash_depends_on_salt_and_hides_address():
    one = hash_ip("203.0.113.9", "salt-a")

    assert one == hash_ip("203.0.113.9", "salt-a")
    assert one != hash_ip("203.0.113.9", "salt-b")
    assert "203.0.113.9" not in one


def test_mask_email_keeps_first_char_and_domain():
    assert mask_email("zhang@example.org") == "z***@example.org"
    assert mask_email("broken") == "***"


def test_email_validation():
    assert is_valid_email("a.b+c@mail.example.cn")
    assert not is_valid_email("a@b") and not is_valid_email("no-at.example.com")


def test_links_use_public_base_url_or_relative_path():
    assert register_link("https://fp.example.com/", "a+b") == (
        "https://fp.example.com/register?code=a%2Bb"
    )
    assert referral_link("", "ABCD2345") == "/apply?ref=ABCD2345"


def test_approved_notice_has_link_and_expiry_only():
    expires = datetime(2026, 9, 28, 10, 30, tzinfo=TZ)

    notice = approved_notice("张三", "https://x/register?code=abc", expires)

    assert notice.link in notice.body
    assert "2026年09月28日 10:30" in notice.body
    assert notice.subject == "【发票报销管理】你的使用申请已通过"


def test_daily_task_survives_errors_and_stops():
    calls: list[int] = []

    def flaky() -> None:
        calls.append(1)
        raise RuntimeError("boom")

    task = DailyTask(flaky)
    task.run_once()  # 异常只记日志，不抛出
    task.start()
    task.stop()

    assert len(calls) >= 1 and not task.is_running
