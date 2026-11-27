"""从历史识别原文补齐实际住宿区间；只写有证据的空字段。"""

import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.db.models import AppSetting, Attachment, EvidenceData, InvoiceData
from invoice_sorting.evidence.lines import lines_from_text
from invoice_sorting.evidence.parsing import find_all_dates
from invoice_sorting.evidence.recognizers.hotel_booking import (
    CHECK_IN_LABEL,
    CHECK_OUT_LABEL,
    NIGHTS_RE,
)
from invoice_sorting.evidence.recognizers.travel_text import (
    after,
    labeled_date,
    labeled_value,
    year_hint,
)
from invoice_sorting.importer.items import item_from_attachment, parse_day

BACKFILL_KEY = "lodging_dates_backfill_version"
BACKFILL_VERSION = "1"
MAX_NIGHTS = 365
logger = logging.getLogger(__name__)


def _extract_dates(raw_text: str, known_check_in: date | None) -> tuple[str, str, str]:
    doc = lines_from_text(raw_text)
    # 旧文件只有“11月1日”时不能用开票日期或升级当天年份猜测入住年。
    if known_check_in is None and not find_all_dates(labeled_value(doc, CHECK_IN_LABEL)):
        return "", "", ""
    year = known_check_in.year if known_check_in else year_hint(doc)
    check_in = known_check_in or labeled_date(doc, CHECK_IN_LABEL, year)
    check_out = after(labeled_date(doc, CHECK_OUT_LABEL, year), check_in)
    nights = NIGHTS_RE.search(doc.text)
    count = int(nights.group(1)) if nights else 0
    if check_in and not check_out:
        check_out = check_in + timedelta(days=count if 1 <= count <= MAX_NIGHTS else 1)
    if check_in and check_out and 0 < (check_out - check_in).days <= MAX_NIGHTS:
        count = (check_out - check_in).days
    else:
        check_out = None
        count = 0
    return (
        check_in.isoformat() if check_in else "",
        check_out.isoformat() if check_out else "",
        str(count) if count else "",
    )


def _fill(details: dict | None, raw_text: str) -> dict[str, str]:
    result = dict(details or {})
    known_check_in = parse_day(result.get("check_in"))
    check_in_text, check_out_text, nights_text = (
        _extract_dates(raw_text, known_check_in) if raw_text else ("", "", "")
    )
    if not result.get("check_in") and check_in_text:
        result["check_in"] = check_in_text
    check_in = parse_day(result.get("check_in"))
    check_out = parse_day(result.get("check_out"))
    if check_in and not result.get("check_out"):
        if check_out_text and check_in_text == result.get("check_in"):
            result["check_out"] = check_out_text
        else:
            nights = result.get("nights") or nights_text
            count = int(nights) if str(nights).isdigit() else 1
            if 1 <= count <= MAX_NIGHTS:
                result["check_out"] = (check_in + timedelta(days=count)).isoformat()
    check_out = parse_day(result.get("check_out"))
    if check_in and check_out and not result.get("nights"):
        count = (check_out - check_in).days
        if 1 <= count <= MAX_NIGHTS:
            result["nights"] = str(count)
    return result


def _old_hotel_order(attachment: Attachment, evidence: EvidenceData) -> bool:
    """旧识别器可能只记录 order，原文中的住宿锚点仍可用于补全。"""
    text = evidence.raw_text or ""
    return bool(
        attachment.kind == AttachmentKind.ORDER
        and evidence.doc_type == "order"
        and ("酒店" in text or "住宿" in text or "hotel" in text.lower())
        and ("入住" in text or "check-in" in text.lower() or "check in" in text.lower())
    )


def backfill_lodging_dates(session: Session) -> int:
    """每账套仅执行一次；不重跑 OCR、不改开票日或人工已填的字段。"""
    marker = session.get(AppSetting, BACKFILL_KEY)
    if marker is not None and marker.value == BACKFILL_VERSION:
        return 0
    query = select(Attachment).options(
        selectinload(Attachment.evidence_data), selectinload(Attachment.invoice_data)
    )
    changed = 0
    rows = session.scalars(query.order_by(Attachment.id).execution_options(yield_per=200))
    for attachment in rows:
        item = item_from_attachment(attachment)
        evidence: EvidenceData | None = attachment.evidence_data
        invoice: InvoiceData | None = attachment.invoice_data
        if evidence is not None and (item.is_hotel_order or _old_hotel_order(attachment, evidence)):
            details = _fill(evidence.details, evidence.raw_text or "")
            if details != (evidence.details or {}):
                evidence.details = details
                check_in = parse_day(details.get("check_in"))
                check_out = parse_day(details.get("check_out"))
                if check_in and (evidence.occurred_on is None or evidence.occurred_on == check_out):
                    evidence.occurred_on = check_in
                changed += 1
        elif invoice is not None and item.is_lodging_invoice:
            details = _fill(invoice.details, invoice.raw_text or "")
            if details != (invoice.details or {}):
                invoice.details = details
                changed += 1
    session.merge(AppSetting(key=BACKFILL_KEY, value=BACKFILL_VERSION))
    session.commit()
    if changed:
        logger.info("历史住宿日期已补全：%s 份凭证", changed)
    return changed
