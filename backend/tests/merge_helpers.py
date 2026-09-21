"""合并导入测试辅助：造一个“什么都有”的虚构账本、导出、开通目标账套、拍与 id 无关的快照。

测试数据全部虚构：商家、发票号码、人名均为编造，不含任何真实发票信息。
"""

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from invoice_sorting.attachments.storage import sha256_of, store_file
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.config import Settings
from invoice_sorting.control.repository import ensure_tenant
from invoice_sorting.db.models import (
    Attachment,
    Batch,
    Category,
    ChecklistItem,
    ChecklistRule,
    EvidenceData,
    Expense,
    ExportRecord,
    InvoiceData,
    ItemMemory,
    MerchantMemory,
    Project,
    StatusEvent,
    User,
)
from invoice_sorting.migration.export import export_tenant

SOURCE_SLUG = "default"
SOURCE_NAME = "虚构来源账套"
BATCH_NAME = "虚构2026-09第1批"
BATCH_CREATED = datetime(2026, 9, 15, 10, 30, 0)
CUSTOM_CATEGORY = "虚构专项"
CUSTOM_PROJECT = "虚构课题"
PERSON = "zhang"
PERSON_NAME = "虚构张三"

# (商家, 金额分, 支出日期, 发票号码)
INVOICED: tuple[tuple[str, int, date, str], ...] = (
    ("虚构文具行", 12800, date(2026, 9, 11), "99000000000000000001"),
    ("虚构书店", 45600, date(2026, 9, 12), "99000000000000000002"),
    ("虚构咖啡馆", 3250, date(2026, 9, 13), "99000000000000000003"),
)
BARE = ("虚构停车场", 1000, date(2026, 9, 14), "停车费")
DELETED = ("虚构已删除商家", 777, date(2026, 9, 10))
EXTRA = ("虚构打印店", 2200, date(2026, 9, 16), "99000000000000000004")


def fake_pdf(directory: Path, name: str, filler: str) -> Path:
    """内容各不相同的虚构 PDF（附件按内容哈希判重，内容必须唯一）。"""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    body = "%PDF-1.4\n% 虚构测试文件\n".encode() + filler.encode() * 32 + b"\n%%EOF\n"
    path.write_bytes(body)
    return path


def open_target(app: Any, slug: str, name: str = "虚构目标账套"):
    """开通一个空账套（控制库登记 + 业务库建好），返回其运行时句柄。"""
    with app.state.control_session_factory() as control:
        ensure_tenant(control, slug, name)
        control.commit()
    return app.state.tenants.get(slug)


def add_invoiced_expense(  # noqa: PLR0913
    db: Session,
    settings: Settings,
    source_dir: Path,
    spec: tuple[str, int, date, str],
    **fields: Any,
) -> Expense:
    merchant, cents, spent_on, invoice_no = spec
    expense = Expense(spent_on=spent_on, amount_cents=cents, merchant=merchant, **fields)
    db.add(expense)
    db.flush()
    pdf = fake_pdf(source_dir, f"{merchant}.pdf", f"发票{invoice_no}")
    attachment = store_file(
        db, settings, pdf, f"{merchant}-发票.pdf", AttachmentKind.INVOICE, expense
    )
    attachment.invoice_data = InvoiceData(
        invoice_no=invoice_no, total_cents=cents, seller_name=merchant, confirmed=True
    )
    db.flush()
    return expense


def seed_rich_ledger(db: Session, settings: Settings, source_dir: Path) -> None:
    """记录、附件文件、发票与凭证数据、批次、清单项、时间线、分类记忆、自定义分类与规则、人。"""
    person = User(username=PERSON, display_name=PERSON_NAME, role="member")
    category = Category(name=CUSTOM_CATEGORY, color="pink", keywords=["虚构关键词"])
    project = Project(code="XK-001", name=CUSTOM_PROJECT)
    db.add_all([person, category, project])
    db.flush()
    db.add(ChecklistRule(category_id=category.id, attachment_kind="contract", hint="虚构提示"))
    batch = Batch(name=BATCH_NAME, project_id=project.id, created_by_id=person.id)
    batch.created_at = BATCH_CREATED
    db.add(batch)
    db.flush()
    common = {"category_id": category.id, "batch_id": batch.id, "created_by_id": person.id}
    for spec in INVOICED:
        expense = add_invoiced_expense(db, settings, source_dir, spec, **common)
        _add_side_rows(db, expense, person.id)
    _add_order_evidence(db, settings, source_dir, expense)
    merchant, cents, spent_on, summary = BARE
    db.add(Expense(spent_on=spent_on, amount_cents=cents, merchant=merchant, summary=summary))
    merchant, cents, spent_on = DELETED
    db.add(Expense(spent_on=spent_on, amount_cents=cents, merchant=merchant, deleted=True))
    loose = fake_pdf(source_dir, "虚构待归属.pdf", "待归属附件")
    store_file(db, settings, loose, "虚构待归属.pdf", AttachmentKind.OTHER, None)
    _add_export_record(db, settings, batch)
    db.add(MerchantMemory(seller_name="虚构文具行", category_id=category.id))
    db.add(ItemMemory(item_name="虚构笔记本", category_id=category.id))
    db.commit()


def _add_side_rows(db: Session, expense: Expense, actor_id: int) -> None:
    db.add(ChecklistItem(expense_id=expense.id, attachment_kind="invoice", state="present"))
    db.add(ChecklistItem(expense_id=expense.id, attachment_kind="order", state="missing"))
    db.add(StatusEvent(expense_id=expense.id, to_status="spent", actor_id=actor_id))
    db.add(StatusEvent(expense_id=expense.id, from_status="spent", to_status="invoiced"))


def _add_order_evidence(
    db: Session, settings: Settings, source_dir: Path, expense: Expense
) -> None:
    pdf = fake_pdf(source_dir, "虚构订单.pdf", "订单截图")
    order = store_file(db, settings, pdf, "虚构订单.pdf", AttachmentKind.ORDER, expense)
    order.evidence_data = EvidenceData(doc_type="order", amount_cents=3250, order_no="XO-0001")
    db.flush()


def _add_export_record(db: Session, settings: Settings, batch: Batch) -> None:
    package = settings.packages_dir / "虚构资料包_20260915" / "资料包.zip"
    package.parent.mkdir(parents=True, exist_ok=True)
    package.write_bytes("PK\x03\x04 虚构资料包".encode().ljust(64, b"\x00"))
    db.add(
        ExportRecord(
            batch_id=batch.id,
            layout="by_expense",
            file_path=package.relative_to(settings.data_dir).as_posix(),
            sha256=sha256_of(package),
            item_count=3,
            total_cents=sum(spec[1] for spec in INVOICED),
        )
    )


def export_source(app: Any, out: Path, slug: str = SOURCE_SLUG) -> Path:
    export_tenant(
        app.state.tenants.get(slug), out, tenant_name=SOURCE_NAME, exported_by="虚构管理员"
    )
    return out


@dataclass(frozen=True)
class LedgerDigest:
    """与 id、路径无关的账本内容：两个账本内容一致时摘要相等。"""

    expenses: frozenset[tuple]
    total_cents: int
    files: frozenset[tuple]
    evidence: int
    checklist: int
    events: int
    batches: frozenset[str]
    exports: int
    memories: frozenset[tuple]


def _count(db: Session, model: type) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def digest(db: Session, settings: Settings) -> LedgerDigest:
    expenses = list(db.scalars(select(Expense).where(Expense.deleted.is_(False))))
    files = frozenset(
        (
            sha256_of(settings.data_dir / item.file_path),
            item.size,
            item.original_name,
            item.invoice_data.invoice_no if item.invoice_data else None,
            item.expense.merchant if item.expense else None,
        )
        for item in db.scalars(select(Attachment))
    )
    memories = {
        ("m", row.seller_name, row.category_id) for row in db.scalars(select(MerchantMemory))
    }
    memories |= {("i", row.item_name, row.category_id) for row in db.scalars(select(ItemMemory))}
    return LedgerDigest(
        expenses=frozenset(
            (e.merchant, e.amount_cents, e.spent_on, e.summary, e.status) for e in expenses
        ),
        total_cents=sum(e.amount_cents for e in expenses),
        files=files,
        evidence=_count(db, EvidenceData),
        checklist=_count(db, ChecklistItem),
        events=_count(db, StatusEvent),
        batches=frozenset(db.scalars(select(Batch.name))),
        exports=_count(db, ExportRecord),
        memories=frozenset((kind, key, _category_name(db, cid)) for kind, key, cid in memories),
    )


def _category_name(db: Session, category_id: int) -> str:
    return db.get(Category, category_id).name


def digest_of(context) -> LedgerDigest:  # noqa: ANN001 - TenantContext
    with context.session_factory() as db:
        return digest(db, context.settings)


def library_files(settings: Settings) -> frozenset[str]:
    return frozenset(
        path.relative_to(settings.data_dir).as_posix()
        for path in settings.library_dir.rglob("*")
        if path.is_file()
    )
