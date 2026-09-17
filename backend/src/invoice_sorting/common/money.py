"""金额工具：统一以“分”为整数存储，禁止浮点运算。"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


def yuan_to_cents(value: str | int | Decimal) -> int:
    """把“960.00”“¥1,234.5”“1234”等元金额转为分。无法解析时抛 ValueError。"""
    if isinstance(value, int):
        return value * 100
    text = str(value).strip().replace("¥", "").replace("￥", "").replace(",", "")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"无法解析金额：{value!r}") from exc
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def cents_to_yuan(cents: int) -> str:
    """分 → “960.00”（无千分位，用于文件名与表格）。"""
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"
