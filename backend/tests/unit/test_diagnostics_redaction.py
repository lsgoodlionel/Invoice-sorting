"""脱敏规则与残留自检（设计《日志与故障上报》4 脱敏）。

测试里出现的邮箱、手机号、卡号等都是**编造的示例值**，不是真实用户数据。
"""

from invoice_sorting.diagnostics.redaction import find_residue, redact_text


def test_replaces_email_with_placeholder() -> None:
    # Arrange
    raw = "导入失败，来信人 zhang.san@example-corp.cn 的附件损坏"

    # Act
    cleaned = redact_text(raw)

    # Assert
    assert "zhang.san@example-corp.cn" not in cleaned
    assert "<邮箱>" in cleaned


def test_replaces_mobile_and_id_card() -> None:
    cleaned = redact_text("联系人 13812345678，证件 110105199003071234")

    assert "13812345678" not in cleaned
    assert "110105199003071234" not in cleaned
    assert "<手机号>" in cleaned
    assert "<证件号>" in cleaned


def test_replaces_bank_card_number() -> None:
    cleaned = redact_text("付款卡号 6222021234567890123 已扣款")

    assert "6222021234567890123" not in cleaned
    assert "<卡号>" in cleaned


def test_replaces_secret_key_value_pairs() -> None:
    raw = '{"api_key": "AKIDzzzzzzzzzzzzzzzz", "password": "hunter2", "cookie": "sid=abc"}'

    cleaned = redact_text(raw)

    assert "AKIDzzzzzzzzzzzzzzzz" not in cleaned
    assert "hunter2" not in cleaned
    assert "sid=abc" not in cleaned
    assert cleaned.count("<已隐去>") == 3
    # 键名保留，方便判断“哪一项配错了”
    assert "api_key" in cleaned and "password" in cleaned


def test_replaces_github_token_shapes() -> None:
    raw = "Authorization: Bearer ghp_0123456789abcdefghijklmnopqrstuvwxyz"

    cleaned = redact_text(raw)

    assert "ghp_" not in cleaned
    assert "<已隐去>" in cleaned


def test_replaces_long_random_strings() -> None:
    cleaned = redact_text("残留串 " + "A1b2C3d4E5" * 5)

    assert "A1b2C3d4E5A1b2C3d4E5" not in cleaned
    assert "<已隐去>" in cleaned


def test_keeps_private_ip_segment_and_hides_public_ip() -> None:
    cleaned = redact_text("内网 192.168.31.24 回源到 203.0.113.9 失败")

    assert "192.168.x.x" in cleaned
    assert "192.168.31.24" not in cleaned
    assert "203.0.113.9" not in cleaned
    assert "<IP>" in cleaned


def test_replaces_username_in_absolute_path() -> None:
    cleaned = redact_text("FileNotFoundError: /home/zhangsan/InvoiceSorting/data")

    assert "/home/<用户>/InvoiceSorting/data" in cleaned


def test_keeps_stack_frame_module_path_and_line_number() -> None:
    raw = '  File "/opt/invoice-sorting/app/backend/src/invoice_sorting/main.py", line 137, in run'

    cleaned = redact_text(raw)

    assert "invoice_sorting/main.py" in cleaned
    assert "line 137" in cleaned
    assert "in run" in cleaned


def test_replaces_evidence_filename_but_keeps_extension_and_type_word() -> None:
    cleaned = redact_text("已归档 北京朝阳饭店住宿发票扫描件.pdf")

    assert "北京朝阳饭店" not in cleaned
    assert cleaned.endswith(".pdf")
    assert "<文件名>" in cleaned
    assert "发票" in cleaned  # 类型词保留，便于判断是哪类凭证出的问题


def test_replaces_merchant_and_guest_names() -> None:
    cleaned = redact_text("销售方：北京某某科技有限公司 入住人=李四")

    assert "北京某某科技有限公司" not in cleaned
    assert "李四" not in cleaned
    assert cleaned.count("<名称>") == 2


def test_replaces_amounts_with_currency_marker() -> None:
    cleaned = redact_text("合计 ¥1,234.56，税额 12.34 元")

    assert "1,234.56" not in cleaned
    assert "12.34" not in cleaned
    assert "<数字>" in cleaned


def test_replaces_invoice_and_order_numbers() -> None:
    cleaned = redact_text("发票号码 24312000000123456789 订单号 A20260920001")

    assert "24312000000123456789" not in cleaned
    assert "A20260920001" not in cleaned
    assert "<发票号>" in cleaned


def test_keeps_sql_structure_and_drops_literal_values() -> None:
    raw = "SELECT id FROM expense WHERE merchant = '北京朝阳饭店' AND amount_cents = 12345"

    cleaned = redact_text(raw)

    assert "SELECT id FROM expense WHERE" in cleaned
    assert "北京朝阳饭店" not in cleaned


def test_replaces_public_hostname_but_keeps_localhost() -> None:
    cleaned = redact_text("upstream kehua.client-corp.cn 超时，本地 localhost 正常")

    assert "kehua.client-corp.cn" not in cleaned
    assert "localhost" in cleaned


def test_redacting_twice_is_stable() -> None:
    once = redact_text("联系人 13812345678 邮箱 a@b.cn")

    assert redact_text(once) == once


def test_find_residue_reports_each_leaked_type() -> None:
    residue = find_residue("a@b.cn 13812345678 6222021234567890123")

    assert set(residue) == {"邮箱", "手机号", "银行卡号"}


def test_find_residue_is_empty_after_redaction() -> None:
    raw = "用户 li@example.cn 手机 13900001111 卡号 6222021234567890123 token=ghp_" + "a" * 36

    assert find_residue(redact_text(raw)) == ()


def test_find_residue_detects_token_shape() -> None:
    residue = find_residue("Bearer ghp_0123456789abcdefghijklmnopqrstuvwxyz")

    assert "密钥形态" in residue
