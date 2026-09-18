"""酒店订单与交通凭证识别器共用：标签取值、缺年份日期、平台名、details 整理。"""

import re
from datetime import date

from invoice_sorting.evidence.lines import EvidenceText
from invoice_sorting.evidence.parsing import find_all_dates, normalize

MONTH_DAY_RE = re.compile(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})\s*日")
CJK_RUN_RE = re.compile(r"[一-鿿·]{2,20}")
LATIN_NAME_RE = re.compile(r"[A-Za-z][A-Za-z .'/-]{1,40}")
VALUE_SEPARATOR_RE = re.compile(r"\s{2,}|[,，;；|(（]")
MAX_NAME_CHARS = 40

PlatformTable = tuple[tuple[str, str], ...]  # (小写/正则关键词, 平台名)


def labeled_value(doc: EvidenceText, label: str) -> str:
    """标签右侧的值；标签独占一行时取下一行（如“入住人”下一行是姓名）。"""
    regex = re.compile(label, re.IGNORECASE)
    lines = doc.lines
    for index, line in enumerate(lines):
        match = regex.search(line.text)
        if not match:
            continue
        value = line.text[match.end() :].strip(" :：")
        if value:
            return value
        if index + 1 < len(lines) and not line.text[: match.start()].strip():
            return lines[index + 1].text.strip()
    return ""


def first_labeled(doc: EvidenceText, labels: tuple[str, ...]) -> str:
    """按优先级依次尝试标签，返回第一个非空值。"""
    return next((value for value in (labeled_value(doc, label) for label in labels) if value), "")


def year_hint(doc: EvidenceText) -> int:
    """文档中第一个完整日期的年份（用于“09月10日”这类缺年份日期），无则取今年。"""
    dates = find_all_dates(doc.text)
    return dates[0].year if dates else date.today().year


def _month_day(text: str, year: int) -> date | None:
    match = MONTH_DAY_RE.search(normalize(text))
    if not match:
        return None
    try:
        return date(year, int(match.group(1)), int(match.group(2)))
    except ValueError:
        return None


def find_date(text: str | None, year: int) -> date | None:
    """完整日期优先，否则按“M月D日”+ year 解析。"""
    if not text:
        return None
    dates = find_all_dates(text)
    return dates[0] if dates else _month_day(text, year)


def labeled_date(doc: EvidenceText, label: str, year: int) -> date | None:
    """所有匹配标签的行中，标签右侧第一个可解析的日期。"""
    regex = re.compile(label, re.IGNORECASE)
    for line in doc.lines:
        for match in regex.finditer(line.text):
            found = find_date(line.text[match.end() :], year)
            if found:
                return found
    return None


def after(later: date | None, earlier: date | None) -> date | None:
    """缺年份导致“离店早于入住”（跨年）时顺延一年。"""
    if later is None or earlier is None or later > earlier:
        return later
    try:
        return later.replace(year=later.year + 1)
    except ValueError:
        return later


def person_name(value: str) -> str:
    """值文本开头的人名：中文取连续汉字，英文取到分隔符为止。"""
    text = value.strip()
    cjk = CJK_RUN_RE.match(text)
    if cjk:
        return cjk.group(0)
    latin = LATIN_NAME_RE.match(VALUE_SEPARATOR_RE.split(text, maxsplit=1)[0])
    return latin.group(0).strip()[:MAX_NAME_CHARS] if latin else ""


def platform_of(text: str, table: PlatformTable) -> str:
    """按表顺序查找平台关键词（正则，忽略大小写）。"""
    return next((name for key, name in table if re.search(key, text, re.IGNORECASE)), "")


def compact_details(values: dict[str, str | None]) -> dict[str, str]:
    """去掉空值，值统一为字符串。"""
    return {key: str(value) for key, value in values.items() if value}
