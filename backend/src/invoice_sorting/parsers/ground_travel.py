"""汽车票、船票（及带“交通工具类型”表格的旅客运输服务数电票）的出行信息。

普通发票解析器不产出 travel；这里从发票文本识别出行信息，识别不出交通工具时返回 None。
注意：网约车/出租车发票也是“*运输服务*客运服务费”，因此不以“客运”二字判断汽车票。
"""

import re
from dataclasses import replace

from invoice_sorting.parsers.base import ParsedInvoice
from invoice_sorting.parsers.text_utils import DATE_PATTERN, compact, make_date, normalize_text

VEHICLE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("bus", ("汽车票", "公路客运", "汽车客运", "道路客运", "长途汽车", "客运站")),
    ("ship", ("船票", "水路客运", "水路旅客", "轮渡", "客轮")),
)
TABLE_VEHICLES: dict[str, str] = {
    "汽车": "bus",
    "客车": "bus",
    "船舶": "ship",
    "轮船": "ship",
    "船": "ship",
    "火车": "train",
    "飞机": "flight",
}
TABLE_HEADER_KEYS: dict[str, str] = {
    "出行人": "passenger",
    "出行日期": "date",
    "出发地": "from",
    "到达地": "to",
    "交通工具类型": "vehicle",
}
PLACE = r"([一-鿿]{2,16})"
FROM_RE = re.compile(r"(?:起点站?|起始站|始发站|出发地|上车站|出发港)\s*:?\s*" + PLACE)
TO_RE = re.compile(r"(?:终点站?|到达站|到达地|下车站|目的地|到达港)\s*:?\s*" + PLACE)
DATE_RE = re.compile(
    r"(?:乘车日期|乘船日期|开航日期|发车日期|出行日期|乘车时间)\s*:?\s*" + DATE_PATTERN
)
PASSENGER_RE = re.compile(r"(?:乘车人|乘船人|出行人|旅客姓名|乘客)\s*:?\s*([一-鿿·]{2,20})")
NUMBER_RE = re.compile(r"(?:班次|航次|车次)\s*:?\s*([A-Za-z0-9]{1,10})")


def _keyword_vehicle(text: str) -> str:
    flat = compact(text)
    return next((name for name, words in VEHICLE_KEYWORDS if any(w in flat for w in words)), "")


def _table_fields(text: str) -> dict[str, str]:
    """数电票“特定业务”表格：表头行下一行按列对应取值；列数不齐时放弃。"""
    lines = text.splitlines()
    for index, line in enumerate(lines[:-1]):
        header = line.split()
        if "出行人" not in header or "交通工具类型" not in header:
            continue
        values = lines[index + 1].split()
        if len(values) != len(header):
            return {}
        pairs = zip(header, values, strict=True)
        return {
            TABLE_HEADER_KEYS[name]: value for name, value in pairs if name in TABLE_HEADER_KEYS
        }
    return {}


def _iso_date(value: str) -> str:
    match = re.search(DATE_PATTERN, value)
    day = make_date(*match.groups()) if match else None
    return day.isoformat() if day else ""


def _labeled_fields(text: str) -> dict[str, str]:
    date_match = DATE_RE.search(text)
    found = {
        "from": FROM_RE.search(text),
        "to": TO_RE.search(text),
        "passenger": PASSENGER_RE.search(text),
        "train_or_flight": NUMBER_RE.search(text),
    }
    fields = {key: match.group(1) for key, match in found.items() if match}
    return {**fields, "date": _iso_date(date_match.group(0)) if date_match else ""}


def detect_ground_travel(text: str) -> dict[str, str] | None:
    """识别汽车票/船票等的出行信息（键同 ParsedInvoice.travel，另含 vehicle）；否则 None。"""
    normalized = normalize_text(text or "")
    table = _table_fields(normalized)
    vehicle = TABLE_VEHICLES.get(table.get("vehicle", ""), "") or _keyword_vehicle(normalized)
    if not vehicle:
        return None
    from_table = {
        key: _iso_date(value) if key == "date" else value
        for key, value in table.items()
        if key != "vehicle"
    }
    fields = {**_labeled_fields(normalized), **from_table}
    return {"vehicle": vehicle, **{key: value for key, value in fields.items() if value}}


def with_ground_travel(parsed: ParsedInvoice) -> ParsedInvoice:
    """解析结果没有 travel 时尝试从文本补充；识别不出返回原对象。"""
    if parsed.travel is not None:
        return parsed
    travel = detect_ground_travel(parsed.raw_text)
    return replace(parsed, travel=travel) if travel else parsed
