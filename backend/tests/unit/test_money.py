import pytest

from invoice_sorting.common.money import cents_to_yuan, yuan_to_cents


@pytest.mark.parametrize(
    ("raw", "cents"),
    [("960.00", 96000), ("¥1,234.5", 123450), (12, 1200), ("999.995", 100000), ("-10.01", -1001)],
)
def test_yuan_to_cents_parses_common_formats(raw, cents):
    assert yuan_to_cents(raw) == cents


def test_yuan_to_cents_rejects_garbage():
    with pytest.raises(ValueError):
        yuan_to_cents("abc")


@pytest.mark.parametrize(("cents", "text"), [(96000, "960.00"), (5, "0.05"), (-1001, "-10.01")])
def test_cents_to_yuan_formats_two_decimals(cents, text):
    assert cents_to_yuan(cents) == text
