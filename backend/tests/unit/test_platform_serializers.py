"""授权密钥的生成与脱敏：密钥必须足够随机，展示时只留前后各 4 位。"""

from invoice_sorting.platform_admin.licenses import generate_license_key
from invoice_sorting.platform_admin.serializers import mask_license_key


def test_generated_keys_are_unique_and_long_enough():
    keys = {generate_license_key() for _ in range(200)}

    assert len(keys) == 200
    assert all(len(key) >= 24 for key in keys)


def test_generated_keys_are_grouped_for_reading():
    key = generate_license_key()

    assert "-" in key
    assert all(part.isalnum() for part in key.split("-"))


def test_mask_keeps_only_four_characters_on_each_side():
    assert mask_license_key("ABCD1234EFGH5678") == "ABCD****5678"


def test_short_keys_are_fully_hidden():
    assert mask_license_key("ABCD5678") == "****"
    assert mask_license_key("") == "****"
