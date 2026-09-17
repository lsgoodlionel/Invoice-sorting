"""分文件导入的中文识别结论（ImportFileResult.recognized_as）。"""

from invoice_sorting.attachments.serializers import kind_label
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.db.models import Attachment

UNRECOGNIZED = "未识别"
INVOICE_LABEL = AttachmentKind.INVOICE.label
RECOGNIZER_LABELS: dict[str, str] = {
    "jd_order": "电商订单",
    "app_store_order": "App Store 订单",
    "receipt": "收据/账单",
    "bank_transaction": "银行交易",
    "wallet_bill": "微信/支付宝账单",
    "ride_itinerary": "打车行程单",
    "filename": "按文件名判断",
}


def _with_detail(label: str, detail: str) -> str:
    # 票种本身可能带括号（如“数电发票（普通发票）”），展开为间隔号避免括号嵌套
    flat = detail.replace("（", "·").replace("(", "·").rstrip("）)")
    return f"{label}（{flat}）" if flat else label


def recognized_as(attachment: Attachment | None) -> str:
    """发票 →“发票（票种）”；凭证 →“类型（识别器）”；其他 →“未识别”。"""
    if attachment is None:
        return UNRECOGNIZED
    invoice = attachment.invoice_data
    if invoice is not None:
        return _with_detail(INVOICE_LABEL, invoice.invoice_type or "")
    evidence = attachment.evidence_data
    recognizer = evidence.recognizer if evidence is not None else ""
    if attachment.kind == AttachmentKind.OTHER:
        return UNRECOGNIZED
    return _with_detail(kind_label(attachment.kind), RECOGNIZER_LABELS.get(recognizer, ""))
