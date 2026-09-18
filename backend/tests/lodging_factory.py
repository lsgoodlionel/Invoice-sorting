"""测试辅助：差旅住宿场景的待归属附件（酒店订单、住宿发票、火车票发票、交通凭证截图）。

直接写入 InvoiceData.details / EvidenceData.details，不依赖识别器进度。
"""

from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select

from invoice_sorting.attachments.storage import store_file
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.db.models import Attachment, Category, EvidenceData, Expense
from tests.evidence_factory import png
from tests.invoice_factory import store_invoice

AUG_15, AUG_16 = date(2026, 8, 15), date(2026, 8, 16)
HOTEL = "苏州园区阳澄湖泰康万豪酒店"
HOTEL_SELLER = "苏州泰康万豪酒店管理有限公司"
ROOM_CENTS = 50000
OUTBOUND_CENTS = 10000
RETURN_CENTS = 12000
_invoice_no = {"value": 0}


def _next_invoice_no() -> str:
    _invoice_no["value"] += 1
    return f"2632200000000{_invoice_no['value']:07d}"


def evidence(
    session, settings, tmp_path: Path, name: str, kind: AttachmentKind, expense=None, **data: Any
) -> Attachment:
    attachment = store_file(session, settings, png(tmp_path / "src", name), name, kind, expense)
    attachment.evidence_data = EvidenceData(confirmed=expense is not None, **data)
    session.flush()
    return attachment


def hotel_order(session, settings, tmp_path: Path, expense: Expense | None = None) -> Attachment:
    details = {
        "city": "苏州",
        "hotel": HOTEL,
        "check_in": "2026-08-15",
        "check_out": "2026-08-16",
        "nights": "1",
        "rooms": "1",
    }
    return evidence(
        session,
        settings,
        tmp_path,
        "酒店订单.png",
        AttachmentKind.ORDER,
        expense,
        doc_type="order",
        recognizer="hotel_booking",
        amount_cents=ROOM_CENTS,
        cny_cents=ROOM_CENTS,
        occurred_on=AUG_16,
        merchant=HOTEL,
        item_name=f"{HOTEL} 08-15–08-16 1晚 1间",
        order_no="1132548283006095",
        details=details,
    )


def _invoice(session, settings, tmp_path: Path, name: str, expense, **fields) -> Attachment:
    data = {"invoice_no": _next_invoice_no(), "confirmed": expense is not None, **fields}
    return store_invoice(session, settings, tmp_path, name=name, invoice=data, expense=expense)


def hotel_invoice(
    session, settings, tmp_path: Path, expense: Expense | None = None, **fields
) -> Attachment:
    base = {
        "issued_on": AUG_16,
        "total_cents": ROOM_CENTS,
        "seller_name": HOTEL_SELLER,
        "item_summary": "住宿费",
        "tax_category": "住宿服务",
    }
    return _invoice(session, settings, tmp_path, "住宿发票.pdf", expense, **{**base, **fields})


def train_invoice(
    session,
    settings,
    tmp_path: Path,
    *,
    returning: bool = False,
    expense: Expense | None = None,
    **details: str,
) -> Attachment:
    route = ("苏州园区", "上海虹桥") if returning else ("上海虹桥", "苏州园区")
    travel = {
        "date": "2026-08-16" if returning else "2026-08-15",
        "from": route[0],
        "to": route[1],
        "vehicle": "train",
        "number": "G7010" if returning else "G7001",
        **details,
    }
    return _invoice(
        session,
        settings,
        tmp_path,
        "返程车票.pdf" if returning else "去程车票.pdf",
        expense,
        issued_on=date(2026, 8, 20),
        total_cents=RETURN_CENTS if returning else OUTBOUND_CENTS,
        seller_name="中国铁路上海局集团有限公司",
        item_summary=f"{route[0]}-{route[1]} {travel['number']}",
        parser="rail_ticket",
        details=travel,
    )


def travel_category(session) -> int:
    return session.scalar(select(Category.id).where(Category.name == "差旅交通"))


def timeline_notes(expense: Expense) -> list[str]:
    return [event.note for event in sorted(expense.status_events, key=lambda e: e.id)]


def checklist_states(expense: Expense) -> dict[str, tuple[str, str]]:
    return {i.attachment_kind: (i.level, i.state) for i in expense.checklist_items}
