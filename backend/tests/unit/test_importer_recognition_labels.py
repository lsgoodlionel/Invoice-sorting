"""分文件导入的中文识别结论。"""

import pytest

from invoice_sorting.db.models import Attachment, EvidenceData, InvoiceData
from invoice_sorting.importer.recognition_labels import UNRECOGNIZED, recognized_as


def attachment(kind: str, recognizer: str | None = None, invoice_type: str | None = None):
    item = Attachment(kind=kind, original_name="a.png", sha256="x", file_path="")
    if recognizer is not None:
        item.evidence_data = EvidenceData(recognizer=recognizer)
    if invoice_type is not None:
        item.invoice_data = InvoiceData(invoice_type=invoice_type)
    return item


@pytest.mark.parametrize(
    ("kind", "recognizer", "expected"),
    [
        ("order", "jd_order", "订单明细（电商订单）"),
        ("order", "app_store_order", "订单明细（App Store 订单）"),
        ("order", "receipt", "订单明细（收据/账单）"),
        ("payment", "bank_transaction", "支付记录（银行交易）"),
        ("payment", "wallet_bill", "支付记录（微信/支付宝账单）"),
        ("itinerary", "ride_itinerary", "行程单（打车行程单）"),
        ("order", "filename", "订单明细（按文件名判断）"),
        ("contract", "none", "合同"),
        ("other", "filename", UNRECOGNIZED),
        ("other", None, UNRECOGNIZED),
    ],
)
def test_evidence_labels(kind, recognizer, expected):
    assert recognized_as(attachment(kind, recognizer)) == expected


def test_invoice_labels_include_invoice_type():
    assert recognized_as(attachment("invoice", invoice_type="数电发票")) == "发票（数电发票）"
    nested = attachment("invoice", invoice_type="数电发票（普通发票）")
    assert recognized_as(nested) == "发票（数电发票·普通发票）"
    assert recognized_as(attachment("invoice", invoice_type="")) == "发票"
    assert recognized_as(None) == UNRECOGNIZED
