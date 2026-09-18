"""全局枚举：状态、附件类型等。值为英文标识（存库/接口），label 为中文显示名。"""

from enum import StrEnum


class ExpenseStatus(StrEnum):
    SPENT = "spent"
    INVOICED = "invoiced"
    COMPLETE = "complete"
    SENT = "sent"
    REIMBURSED = "reimbursed"
    VOID = "void"

    @property
    def label(self) -> str:
        return EXPENSE_STATUS_LABELS[self]

    @property
    def rank(self) -> int:
        """主状态线上的顺序，作废为 -1。"""
        return STATUS_ORDER.index(self) if self in STATUS_ORDER else -1


STATUS_ORDER: tuple[ExpenseStatus, ...] = (
    ExpenseStatus.SPENT,
    ExpenseStatus.INVOICED,
    ExpenseStatus.COMPLETE,
    ExpenseStatus.SENT,
    ExpenseStatus.REIMBURSED,
)

EXPENSE_STATUS_LABELS: dict[ExpenseStatus, str] = {
    ExpenseStatus.SPENT: "已支出",
    ExpenseStatus.INVOICED: "已开票",
    ExpenseStatus.COMPLETE: "凭证齐全",
    ExpenseStatus.SENT: "已外发",
    ExpenseStatus.REIMBURSED: "已报销",
    ExpenseStatus.VOID: "不报销/作废",
}


class AttachmentKind(StrEnum):
    INVOICE = "invoice"
    ORDER = "order"
    PAYMENT = "payment"
    ACCEPTANCE = "acceptance"
    CONTRACT = "contract"
    APPLICATION = "application"
    ITINERARY = "itinerary"
    MEAL_FORM = "meal_form"
    MEETING = "meeting"
    SOFTWARE_FORM = "software_form"
    STATEMENT = "statement"
    TRANSPORT = "transport"
    OTHER = "other"

    @property
    def label(self) -> str:
        return ATTACHMENT_KIND_LABELS[self]


ATTACHMENT_KIND_LABELS: dict[AttachmentKind, str] = {
    AttachmentKind.INVOICE: "发票",
    AttachmentKind.ORDER: "订单明细",
    AttachmentKind.PAYMENT: "支付记录",
    AttachmentKind.ACCEPTANCE: "验收单",
    AttachmentKind.CONTRACT: "合同",
    AttachmentKind.APPLICATION: "申购单",
    AttachmentKind.ITINERARY: "行程单",
    AttachmentKind.MEAL_FORM: "工作餐单",
    AttachmentKind.MEETING: "会议材料",
    AttachmentKind.SOFTWARE_FORM: "软件服务报账单",
    AttachmentKind.STATEMENT: "情况说明",
    AttachmentKind.TRANSPORT: "往来交通凭证",
    AttachmentKind.OTHER: "其他",
}


class ChecklistLevel(StrEnum):
    REQUIRED = "required"
    SUGGESTED = "suggested"


class ChecklistState(StrEnum):
    MISSING = "missing"
    PRESENT = "present"
    NOT_NEEDED = "not_needed"


class BatchStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    PARTIAL = "partial"
    RECEIVED = "received"


BATCH_STATUS_LABELS: dict[BatchStatus, str] = {
    BatchStatus.DRAFT: "待外发",
    BatchStatus.SENT: "已外发",
    BatchStatus.PARTIAL: "部分到账",
    BatchStatus.RECEIVED: "已到账",
}


class ExportLayout(StrEnum):
    BY_EXPENSE = "by_expense"
    BY_KIND = "by_kind"


class DateBasis(StrEnum):
    SPENT = "spent"
    INVOICED = "invoiced"
    SENT = "sent"
    RECEIVED = "received"
