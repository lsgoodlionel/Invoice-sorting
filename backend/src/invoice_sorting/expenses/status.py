"""状态推导：纯函数，集中定义自动状态规则（蓝图第 3 节）。"""

from invoice_sorting.common.constants import ExpenseStatus


def derive_status(
    *, has_invoice: bool, required_missing: int, in_sent_batch: bool, reimbursed: bool
) -> ExpenseStatus:
    """按条件推导自动状态；允许跳级（收到发票时材料已齐可直接到“凭证齐全”）。"""
    if reimbursed:
        return ExpenseStatus.REIMBURSED
    if in_sent_batch:
        return ExpenseStatus.SENT
    if has_invoice and required_missing == 0:
        return ExpenseStatus.COMPLETE
    if has_invoice:
        return ExpenseStatus.INVOICED
    return ExpenseStatus.SPENT
