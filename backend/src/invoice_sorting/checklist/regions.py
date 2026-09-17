"""开票地区与“已带明细平台”判定（纯函数）：外地发票需附网购订单截图，明细平台可免。"""

from collections.abc import Iterable
from dataclasses import dataclass

from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.db.models import Expense, InvoiceData

DEFAULT_LOCAL_REGION = "上海"
DEFAULT_DETAIL_PLATFORMS: tuple[str, ...] = ("京东", "当当", "圆迈")


@dataclass(frozen=True)
class RegionPolicy:
    """本地地区与已带明细平台关键词（来自设置）。"""

    local_region: str = DEFAULT_LOCAL_REGION
    detail_platforms: tuple[str, ...] = DEFAULT_DETAIL_PLATFORMS


DEFAULT_POLICY = RegionPolicy()


def expense_invoices(expense: Expense) -> list[InvoiceData]:
    """记录下已识别的发票数据（按附件 id 排序）。"""
    attachments = sorted(expense.attachments, key=lambda attachment: attachment.id or 0)
    return [
        attachment.invoice_data
        for attachment in attachments
        if attachment.kind == AttachmentKind.INVOICE and attachment.invoice_data is not None
    ]


def is_nonlocal_region(region_name: str | None, local_region: str | None) -> bool:
    """地区非空且与本地地区不同；“上海”与“上海市”视为相同，本地地区为空时不判定。"""
    region, local = (region_name or "").strip(), (local_region or "").strip()
    if not region or not local:
        return False
    return not (region.startswith(local) or local.startswith(region))


def is_detail_seller(seller_name: str | None, platforms: Iterable[str]) -> bool:
    """销售方名称包含任一平台关键词，如“北京京东世纪贸易有限公司”含“京东”。"""
    seller = (seller_name or "").strip()
    return bool(seller) and any(keyword and keyword in seller for keyword in platforms)


def region_name(expense: Expense, local_region: str) -> str:
    """记录的开票地区：优先返回外地地区，否则返回首个非空地区。"""
    regions = [invoice.region_name for invoice in expense_invoices(expense) if invoice.region_name]
    nonlocal_regions = [region for region in regions if is_nonlocal_region(region, local_region)]
    return (nonlocal_regions or regions or [""])[0]


def is_nonlocal(expense: Expense, local_region: str) -> bool:
    """记录任一发票的开票地区非空且不是本地。"""
    return any(
        is_nonlocal_region(invoice.region_name, local_region)
        for invoice in expense_invoices(expense)
    )


def is_detail_platform(expense: Expense, platforms: Iterable[str]) -> bool:
    """记录任一发票的销售方属于已带明细的平台。"""
    keywords = tuple(platforms)
    return any(
        is_detail_seller(invoice.seller_name, keywords) for invoice in expense_invoices(expense)
    )
