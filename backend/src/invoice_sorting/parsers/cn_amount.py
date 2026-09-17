"""中文大写金额 → 分。"""

CN_DIGITS: dict[str, int] = {
    "零": 0,
    "〇": 0,
    "壹": 1,
    "贰": 2,
    "叁": 3,
    "肆": 4,
    "伍": 5,
    "陆": 6,
    "柒": 7,
    "捌": 8,
    "玖": 9,
}
SMALL_UNITS: dict[str, int] = {"拾": 10, "佰": 100, "仟": 1000}
YUAN_MARKS = ("圆", "元")
END_MARKS = ("整", "正")
CN_AMOUNT_CHARS = "".join(CN_DIGITS) + "".join(SMALL_UNITS) + "万亿圆元角分整正"


def _parse_integer_part(text: str) -> int | None:
    total = 0
    section = 0
    number = 0
    for char in text:
        if char in CN_DIGITS:
            number = CN_DIGITS[char]
        elif char in SMALL_UNITS:
            section += (number or 1) * SMALL_UNITS[char]
            number = 0
        elif char == "万":
            total += (section + number) * 10_000
            section = number = 0
        elif char == "亿":
            total = (total + section + number) * 100_000_000
            section = number = 0
        else:
            return None
    return total + section + number


def _parse_fraction_part(text: str) -> int | None:
    cents = 0
    number = 0
    for char in text:
        if char in CN_DIGITS:
            number = CN_DIGITS[char]
        elif char == "角":
            cents += number * 10
            number = 0
        elif char == "分":
            cents += number
            number = 0
        else:
            return None
    return cents if number == 0 else None


def cn_upper_to_cents(text: str) -> int | None:
    """把“玖佰陆拾圆整”“壹万零伍拾元零伍分”等大写金额转为分；无法解析返回 None。"""
    value = "".join(text.split())
    for mark in END_MARKS:
        value = value.replace(mark, "")
    if not value:
        return None
    for mark in YUAN_MARKS:
        value = value.replace(mark, "圆")
    if value.count("圆") > 1:
        return None
    if "圆" in value:
        integer_text, fraction_text = value.split("圆")
    elif "角" in value or "分" in value:
        integer_text, fraction_text = "", value
    else:
        integer_text, fraction_text = value, ""
    integer = _parse_integer_part(integer_text) if integer_text else 0
    fraction = _parse_fraction_part(fraction_text) if fraction_text else 0
    if integer is None or fraction is None:
        return None
    return integer * 100 + fraction
