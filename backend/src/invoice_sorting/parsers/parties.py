"""购买方/销售方：标签与税号模式，以及无坐标时的纯文本兜底提取。"""

import re
from dataclasses import dataclass

from invoice_sorting.parsers.text_utils import normalize_text

# “项目名称”“服务名称”不是购销方标签；标签允许字间空格、冒号可省略（可能在下一行）
NAME_LABEL_RE = re.compile(r"(?<![目务])名\s*称\s*:?\s*")
TAX_ID_LABEL_RE = re.compile(
    r"(?:(?:统\s*一\s*社\s*会\s*信\s*用\s*代\s*码|纳\s*税\s*人\s*识\s*别\s*号)\s*/?\s*)+:?\s*"
)
# 18 位统一社会信用代码（不含 I/O/S/V/Z），或 15/17/20 位旧税号（前 6 位为行政区划码）
TAX_ID_PATTERN = (
    r"(?:[0-9A-HJ-NP-RTUW-Y]{2}\d{6}[0-9A-HJ-NP-RTUW-Y]{10}"
    r"|\d{6}[0-9A-Z]{14}|\d{6}[0-9A-Z]{11}|\d{6}[0-9A-Z]{9})(?![0-9A-Z])"
)
TAX_ID_VALUE_RE = re.compile(r"^[/:\s]*(" + TAX_ID_PATTERN + ")")
PARTY_NOISE_RE = re.compile(r"(?:\s+[购买销售方信息])+$")


@dataclass(frozen=True)
class Parties:
    buyer_name: str
    buyer_tax_id: str
    seller_name: str
    seller_tax_id: str


def tax_id_after_label(text: str) -> str:
    """标签之后紧跟的合法税号；不合法或缺失返回 ""。"""
    match = TAX_ID_VALUE_RE.match(text)
    return match.group(1) if match else ""


def _clean_party_name(value: str) -> str:
    """去掉竖排标签残字（如“销”“售”），并截断到第一个空白（右侧可能并排了其他栏内容）。"""
    tokens = PARTY_NOISE_RE.sub("", " " + value.strip()).split()
    return tokens[0] if tokens else ""


def party_names(text: str) -> list[str]:
    """按阅读顺序列出所有“名称”取值（保留空值占位，便于区分左右）。"""
    names: list[str] = []
    for line in normalize_text(text).splitlines():
        segments = NAME_LABEL_RE.split(line)
        names.extend(_clean_party_name(segment) for segment in segments[1:])
    return names


def party_tax_ids(text: str) -> list[str]:
    ids: list[str] = []
    for line in normalize_text(text).splitlines():
        segments = TAX_ID_LABEL_RE.split(line)
        ids.extend(tax_id_after_label(segment) for segment in segments[1:])
    return ids


def pair_or_empty(values: list[str]) -> tuple[str, str]:
    padded = [*values, "", ""]
    return padded[0], padded[1]


def extract_text_parties(text: str) -> Parties:
    """按文本阅读顺序：第一个为购买方，第二个为销售方。"""
    buyer, seller = pair_or_empty(party_names(text))
    buyer_id, seller_id = pair_or_empty(party_tax_ids(text))
    return Parties(buyer, buyer_id, seller, seller_id)
