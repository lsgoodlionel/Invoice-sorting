"""搬迁测试辅助：构造一个虚构账套（记录、附件文件、批次、导出记录、分类记忆）并拍快照。

测试数据全部虚构，不含任何真实发票信息。
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from invoice_sorting.attachments.storage import sha256_of, store_file
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.config import Settings
from invoice_sorting.db.models import (
    Attachment,
    Batch,
    Category,
    Expense,
    ExportRecord,
    ItemMemory,
    MerchantMemory,
)

SAMPLE_EXPENSES: tuple[tuple[str, int, date], ...] = (
    ("虚构文具行", 12800, date(2026, 9, 11)),
    ("虚构书店", 45600, date(2026, 9, 12)),
    ("虚构咖啡馆", 3250, date(2026, 9, 13)),
)
BATCH_NAME = "虚构九月报销批次"
PACKAGE_DIRNAME = "虚构资料包_20260915"
PACKAGE_FILENAME = "资料包.zip"
PACKAGE_BODY = "PK\x03\x04 虚构资料包占位内容".encode().ljust(64, b"\x00")


@dataclass(frozen=True)
class TenantSnapshot:
    """账套的可比对快照：两次导入导出之间应完全一致。"""

    expenses: int
    total_cents: int
    batches: int
    exports: int
    memories: int
    files: tuple[tuple[str, int, str], ...]  # (相对 data_dir 路径, 字节数, sha256)


def _fake_pdf(directory: Path, name: str, filler: bytes) -> Path:
    """生成内容各不相同的虚构 PDF（附件去重按 sha256，内容必须唯一）。"""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes("%PDF-1.4\n% 虚构测试文件\n".encode() + filler * 32 + b"\n%%EOF\n")
    return path


def seed_tenant_data(session: Session, settings: Settings, source_dir: Path) -> None:
    """写入一整套虚构业务数据并把附件文件真正落到文件库。"""
    category = session.scalars(select(Category).order_by(Category.id)).first()
    batch = Batch(name=BATCH_NAME)
    session.add(batch)
    session.flush()
    for index, (merchant, cents, spent_on) in enumerate(SAMPLE_EXPENSES, start=1):
        expense = Expense(
            spent_on=spent_on,
            amount_cents=cents,
            merchant=merchant,
            category=category,
            batch=batch,
            summary=f"虚构明细 {index}",
        )
        session.add(expense)
        session.flush()
        source = _fake_pdf(source_dir, f"{merchant}.pdf", f"虚构内容{index}".encode())
        store_file(session, settings, source, f"{merchant}.pdf", AttachmentKind.INVOICE, expense)
    _seed_side_tables(session, settings, batch, category)
    session.commit()


def _seed_side_tables(
    session: Session, settings: Settings, batch: Batch, category: Category | None
) -> None:
    package = settings.packages_dir / PACKAGE_DIRNAME / PACKAGE_FILENAME
    package.parent.mkdir(parents=True, exist_ok=True)
    package.write_bytes(PACKAGE_BODY)
    session.add(
        ExportRecord(
            batch_id=batch.id,
            layout="by_expense",
            file_path=package.relative_to(settings.data_dir).as_posix(),
            sha256=sha256_of(package),
            item_count=len(SAMPLE_EXPENSES),
            total_cents=sum(cents for _, cents, _ in SAMPLE_EXPENSES),
        )
    )
    if category is not None:
        session.add(MerchantMemory(seller_name="虚构文具行", category_id=category.id))
        session.add(ItemMemory(item_name="虚构笔记本", category_id=category.id))


def _count(session: Session, model: type) -> int:
    return len(list(session.scalars(select(model))))


def snapshot(session: Session, settings: Settings) -> TenantSnapshot:
    """统计记录数、金额合计与全部附件文件的字节数与校验和。"""
    expenses = list(session.scalars(select(Expense)))
    files = []
    for attachment in session.scalars(select(Attachment).order_by(Attachment.id)):
        path = settings.data_dir / attachment.file_path
        files.append((attachment.file_path, path.stat().st_size, sha256_of(path)))
    return TenantSnapshot(
        expenses=len(expenses),
        total_cents=sum(expense.amount_cents for expense in expenses),
        batches=_count(session, Batch),
        exports=_count(session, ExportRecord),
        memories=_count(session, MerchantMemory) + _count(session, ItemMemory),
        files=tuple(files),
    )


def snapshot_of(app, slug: str) -> TenantSnapshot:
    """按 slug 取租户运行时并拍快照。"""
    context = app.state.tenants.get(slug)
    with context.session_factory() as session:
        return snapshot(session, context.settings)
