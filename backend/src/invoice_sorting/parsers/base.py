"""发票解析的公共数据结构与解析器协议。"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ParsedInvoice:
    invoice_no: str | None
    issued_on: date | None
    total_cents: int | None  # 价税合计，分
    tax_cents: int | None
    amount_cents: int | None  # 不含税金额
    seller_name: str
    seller_tax_id: str
    buyer_name: str
    buyer_tax_id: str
    item_summary: str  # 首个项目名称（去掉 *分类* 前缀）+ “等N项”
    tax_category: str  # 首个项目的 *分类简称*，无则 ""
    invoice_type: str
    parser: str
    warnings: tuple[str, ...]
    raw_text: str
    travel: dict[str, str] | None = None  # 差旅票：date, from, to, passenger, train_or_flight
    region_code: str = ""  # 开票地区的省级行政区划代码前两位，如 "31"；无法判断为 ""
    region_name: str = ""  # 开票地区简称，如 "上海"
    order_no: str = ""  # 票面备注中的电商订单号，如京东“订单号:338623377834”


class InvoiceParser(Protocol):
    name: str

    def can_parse(self, path: Path, text: str | None) -> bool: ...

    def parse(self, path: Path, text: str | None) -> ParsedInvoice: ...


class InvoiceParseError(ValueError):
    """解析器无法从输入中得到有效发票时抛出；由注册表统一捕获。"""
