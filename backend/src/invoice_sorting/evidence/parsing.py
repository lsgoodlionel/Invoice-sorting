"""凭证文本解析工具：容忍 OCR 噪声的金额/币种与日期解析。"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from invoice_sorting.common.money import yuan_to_cents

CNY = "CNY"

# 前缀符号 → ISO 币种；长符号在前，保证 “US$” 优先于 “$”
SYMBOL_CURRENCIES: tuple[tuple[str, str], ...] = (
    ("US$", "USD"),
    ("HK$", "HKD"),
    ("JP¥", "JPY"),
    ("CN¥", "CNY"),
    ("NT$", "TWD"),
    ("A$", "AUD"),
    ("S$", "SGD"),
    ("C$", "CAD"),
    ("RMB", "CNY"),
    ("€", "EUR"),
    ("£", "GBP"),
    ("¥", "CNY"),
    ("$", "USD"),
)
ISO_CURRENCIES = ("CNY", "USD", "EUR", "GBP", "HKD", "JPY", "SGD", "AUD", "CAD", "TWD")

_NUMBER = r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?"
_SYMBOLS = "|".join(re.escape(symbol) for symbol, _ in SYMBOL_CURRENCIES)
_ISO = r"(?<![A-Za-z])(?:" + "|".join(ISO_CURRENCIES) + r")(?![A-Za-z])"
MONEY_RE = re.compile(
    rf"(?P<sym>{_SYMBOLS}|{_ISO})\s*(?P<num>{_NUMBER})(?!\d)"
    rf"|(?<![\d.])(?P<num2>{_NUMBER})\s*(?P<suf>元|{_ISO})"
)

_MONTHS = {
    name: index
    for index, names in enumerate(
        (
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ),
        start=1,
    )
    for name in names
}
_MONTH_NAME = r"(?P<mon>[A-Za-z]{3,9})\.?"
NUMERIC_DATE_RE = re.compile(
    r"(?<!\d)(?P<y>\d{4})\s*[年/.-]\s*(?P<m>\d{1,2})\s*[月/.-]\s*(?P<d>\d{1,2})"
)
ENGLISH_DATE_RE = re.compile(
    rf"{_MONTH_NAME}\s+(?P<d>\d{{1,2}}),?\s+(?P<y>\d{{4}})"
    rf"|(?P<d2>\d{{1,2}})\s+(?P<mon2>[A-Za-z]{{3,9}})\.?,?\s+(?P<y2>\d{{4}})"
)


@dataclass(frozen=True)
class Money:
    cents: int
    currency: str


def normalize(text: str) -> str:
    """NFKC 规范化：全角数字/字母/标点转半角，“￥”→“¥”。"""
    return unicodedata.normalize("NFKC", text)


def _currency_of(marker: str) -> str:
    for symbol, currency in SYMBOL_CURRENCIES:
        if marker == symbol:
            return currency
    return CNY if marker == "元" else marker


def _to_money(match: re.Match[str]) -> Money | None:
    number = match.group("num") or match.group("num2")
    marker = match.group("sym") or match.group("suf")
    try:
        return Money(yuan_to_cents(number), _currency_of(marker))
    except ValueError:
        return None


def find_all_money(text: str | None) -> list[Money]:
    """按出现顺序返回所有带币种标记（符号、ISO 代码或“元”）的金额。"""
    if not text:
        return []
    found = (_to_money(match) for match in MONEY_RE.finditer(normalize(text)))
    return [money for money in found if money is not None]


def find_money(text: str | None) -> Money | None:
    money = find_all_money(text)
    return money[0] if money else None


def _make_date(year: str, month: int | str, day: str) -> date | None:
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def _english_date(match: re.Match[str]) -> date | None:
    month_name = (match.group("mon") or match.group("mon2")).lower()
    month = _MONTHS.get(month_name)
    if month is None:
        return None
    return _make_date(
        match.group("y") or match.group("y2"), month, match.group("d") or match.group("d2")
    )


def find_all_dates(text: str | None) -> list[date]:
    """按出现顺序返回所有可解析日期（数字格式与英文月份格式）。"""
    if not text:
        return []
    flat = normalize(text)
    found: list[tuple[int, date | None]] = [
        (m.start(), _make_date(m.group("y"), m.group("m"), m.group("d")))
        for m in NUMERIC_DATE_RE.finditer(flat)
    ]
    found += [(m.start(), _english_date(m)) for m in ENGLISH_DATE_RE.finditer(flat)]
    return [value for _, value in sorted(found, key=lambda item: item[0]) if value is not None]


def parse_date(text: str | None) -> date | None:
    dates = find_all_dates(text)
    return dates[0] if dates else None


PLAIN_AMOUNT_RE = re.compile(
    r"(?<![\d.])-?\s*(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+\.\d{1,2})(?![\d.])"
)


def find_plain_amount(text: str | None) -> int | None:
    """无币种标记的小数金额（如“-35.00”“1,234.50”），返回分的绝对值。"""
    match = PLAIN_AMOUNT_RE.search(normalize(text or ""))
    return yuan_to_cents(match.group(1)) if match else None


def strip_money(text: str) -> str:
    """去掉文本中带币种标记的金额。"""
    return MONEY_RE.sub("", normalize(text)).strip()
