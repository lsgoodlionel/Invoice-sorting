"""derive_status 表驱动测试。"""

import pytest

from invoice_sorting.common.constants import ExpenseStatus
from invoice_sorting.expenses.status import derive_status

CASES = [
    # has_invoice, required_missing, in_sent_batch, reimbursed, expected
    (False, 0, False, False, ExpenseStatus.SPENT),
    (False, 3, False, False, ExpenseStatus.SPENT),
    (True, 2, False, False, ExpenseStatus.INVOICED),
    (True, 0, False, False, ExpenseStatus.COMPLETE),
    (True, 1, True, False, ExpenseStatus.SENT),
    (False, 0, True, False, ExpenseStatus.SENT),
    (True, 0, True, True, ExpenseStatus.REIMBURSED),
    (False, 5, False, True, ExpenseStatus.REIMBURSED),
]


@pytest.mark.parametrize(("has_invoice", "missing", "sent", "reimbursed", "expected"), CASES)
def test_derive_status_table(has_invoice, missing, sent, reimbursed, expected):
    result = derive_status(
        has_invoice=has_invoice,
        required_missing=missing,
        in_sent_batch=sent,
        reimbursed=reimbursed,
    )
    assert result is expected


def test_derive_status_allows_skipping_directly_to_complete():
    assert (
        derive_status(has_invoice=True, required_missing=0, in_sent_batch=False, reimbursed=False)
        == ExpenseStatus.COMPLETE
    )


@pytest.mark.parametrize(
    ("has_invoice", "evidence", "missing", "expected"),
    [
        (False, False, 0, ExpenseStatus.SPENT),
        (True, False, 0, ExpenseStatus.SPENT),  # 免票记录不看发票
        (False, True, 1, ExpenseStatus.INVOICED),
        (False, True, 0, ExpenseStatus.COMPLETE),
    ],
)
def test_invoice_exempt_uses_order_or_payment_evidence(has_invoice, evidence, missing, expected):
    result = derive_status(
        has_invoice=has_invoice,
        required_missing=missing,
        in_sent_batch=False,
        reimbursed=False,
        invoice_exempt=True,
        has_exempt_evidence=evidence,
    )
    assert result is expected
