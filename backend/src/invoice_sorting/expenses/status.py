"""状态推导：纯函数，集中定义自动状态规则（蓝图第 3 节；免发票记录见设计 v2.1 4.3）。"""

from invoice_sorting.common.constants import ExpenseStatus


def derive_status(
    *,
    has_invoice: bool,
    required_missing: int,
    in_sent_batch: bool,
    reimbursed: bool,
    invoice_exempt: bool = False,
    has_exempt_evidence: bool = False,
) -> ExpenseStatus:
    """按条件推导自动状态；允许跳级（收到发票时材料已齐可直接到“凭证齐全”）。

    免发票记录不看发票，“已有订单/收据或支付记录任一项”视为已开票。
    """
    if reimbursed:
        return ExpenseStatus.REIMBURSED
    if in_sent_batch:
        return ExpenseStatus.SENT
    has_voucher = has_exempt_evidence if invoice_exempt else has_invoice
    if has_voucher and required_missing == 0:
        return ExpenseStatus.COMPLETE
    if has_voucher:
        return ExpenseStatus.INVOICED
    return ExpenseStatus.SPENT
