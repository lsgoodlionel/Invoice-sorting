"""非发票凭证（订单、收据、银行交易、行程单等）识别结果的公共结构。"""

from dataclasses import dataclass, field
from datetime import date

DOC_ORDER = "order"
DOC_RECEIPT = "receipt"
DOC_PAYMENT = "payment"
DOC_ITINERARY = "itinerary"
DOC_UNKNOWN = "unknown"


@dataclass(frozen=True)
class RecognizedEvidence:
    doc_type: str  # order / receipt / payment / itinerary / unknown
    recognizer: str  # jd_order / app_store_order / receipt / bank_transaction / ... / filename
    amount_cents: int | None = None  # 票面金额（按 currency）
    currency: str = "CNY"
    cny_cents: int | None = None  # 人民币金额；外币订单为 None
    occurred_on: date | None = None
    merchant: str = ""
    item_name: str = ""
    order_no: str = ""
    card_last4: str = ""
    is_foreign: bool = False
    raw_text: str = ""
    confidence: float = 0.0  # 0~1，识别器匹配程度
    # 结构化补充信息（键见 docs/差旅住宿凭证_设计.md）：
    #   酒店订单：city、hotel、check_in、check_out（YYYY-MM-DD）、rooms、nights、guest、platform
    #   交通凭证：date（YYYY-MM-DD）、from、to、vehicle（train/flight/bus/ship）、number、passenger
    details: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class FilenameHints:
    kind: str | None  # AttachmentKind 值，如 "order"；无法判断为 None
    category_word: str  # 文件名首段分类词，如 "办公"、"软件"
    amount_cents: int | None
    occurred_on: date | None
    region: str  # 文件名中的地区词，如 "江苏"
    file_key: str  # 文件名键（见设计 3.3）
