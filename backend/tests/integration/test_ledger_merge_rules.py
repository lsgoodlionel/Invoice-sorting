"""合并导入的规则与保护：占位用户、批次改名、冲突保留本地、旧包兼容、版本拒绝、预览不写入、失败回滚。"""

import dataclasses
import json
import zipfile
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from invoice_sorting.attachments.storage import store_file
from invoice_sorting.common.constants import AttachmentKind
from invoice_sorting.control.members import list_members
from invoice_sorting.control.models import ACCOUNT_SOURCE_IMPORT, Account, Membership
from invoice_sorting.control.repository import create_account, find_tenant
from invoice_sorting.db.models import Batch, Category, ChecklistRule, Expense, MerchantMemory, User
from invoice_sorting.migration import merge as engine
from invoice_sorting.migration import merge_apply_records
from invoice_sorting.migration.ledger import LEDGER_NAME
from invoice_sorting.migration.manifest import MANIFEST_NAME
from invoice_sorting.migration.merge import ImportFailedError, merge_import, preview_merge
from invoice_sorting.migration.merge_files import MERGE_STAGING_DIRNAME
from invoice_sorting.migration.package import ImportRejectedError
from invoice_sorting.users.serializers import serialize_member
from tests.merge_helpers import (
    BATCH_NAME,
    CUSTOM_CATEGORY,
    INVOICED,
    PERSON,
    PERSON_NAME,
    SOURCE_NAME,
    digest_of,
    export_source,
    fake_pdf,
    library_files,
    open_target,
    seed_rich_ledger,
)

TARGET = "merge-rules"


@pytest.fixture
def source(app, settings, session, tmp_path):
    seed_rich_ledger(session, settings, tmp_path / "来源")
    return app


@pytest.fixture
def archive(source, tmp_path) -> Path:
    return export_source(source, tmp_path / "包.zip")


def merge(app, path: Path, slug: str = TARGET, include_settings: bool = True):
    return merge_import(
        app.state.tenants, app.state.control_session_factory, path, slug, include_settings
    )


def accounts(app) -> list[tuple[str, bool, str]]:
    with app.state.control_session_factory() as control:
        rows = control.scalars(select(Account).order_by(Account.id))
        return [(row.username, row.is_active, row.source) for row in rows]


def rewrite_archive(path: Path, out: Path, drop: str = "", manifest=None) -> Path:  # noqa: ANN001
    """复制搬迁包：可去掉某个成员、可改写清单（用于模拟旧包与新版本包）。"""
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(out, "w") as target:
        for info in source.infolist():
            if info.filename == drop:
                continue
            data = source.read(info.filename)
            if info.filename == MANIFEST_NAME and manifest is not None:
                data = json.dumps(manifest(json.loads(data)), ensure_ascii=False).encode()
            target.writestr(info, data)
    return out


def test_unknown_person_becomes_disabled_placeholder(source, archive):
    target = open_target(source, TARGET)

    report = merge(source, archive)

    assert (PERSON, False, ACCOUNT_SOURCE_IMPORT) in accounts(source)
    with source.state.control_session_factory() as control:
        account = control.scalars(select(Account).where(Account.username == PERSON)).one()
        tenant = find_tenant(control, TARGET)
        membership = control.scalars(
            select(Membership).where(Membership.account_id == account.id)
        ).one()
        assert (membership.tenant_id, membership.is_active) == (tenant.id, False)
        assert account.password_hash is None and account.display_name == PERSON_NAME
        listed = [serialize_member(member) for member in list_members(control, tenant.id)]
        shown = {(row["username"], row["is_active"], row["source"]) for row in listed}
        assert (PERSON, False, ACCOUNT_SOURCE_IMPORT) in shown  # 用户管理里标注来自导入
    with target.session_factory() as db:
        mirror = db.get(User, account.id)
        assert (mirror.username, mirror.is_active, mirror.display_name) == (
            PERSON,
            False,
            PERSON_NAME,
        )
        creators = {e.created_by_id for e in db.scalars(select(Expense)) if e.batch_id}
        assert creators == {account.id}
    assert report.section("users").added == 1


def test_placeholder_never_reuses_a_taken_username(source, archive):
    with source.state.control_session_factory() as control:
        create_account(control, PERSON, "别的账套的同名人")
        control.commit()
    open_target(source, TARGET)

    merge(source, archive)

    assert (f"{PERSON}.imp", False, ACCOUNT_SOURCE_IMPORT) in accounts(source)
    assert (PERSON, True, "") in accounts(source)  # 原账号不受影响，也没有被拉进目标账套


def test_known_person_is_matched_by_username(source, archive):
    target = open_target(source, TARGET)
    with target.session_factory() as db:
        db.add(User(username=PERSON, display_name="本地张三"))
        db.commit()
    before = accounts(source)

    report = merge(source, archive)

    assert accounts(source) == before
    assert report.section("users").added == 0 and report.section("users").skipped == 1


def test_batch_name_conflict_gets_source_suffix_and_stays_idempotent(source, archive):
    target = open_target(source, TARGET)
    with target.session_factory() as db:
        db.add(Batch(name=BATCH_NAME))
        db.commit()

    merge(source, archive)
    merge(source, archive)

    with target.session_factory() as db:
        names = sorted(db.scalars(select(Batch.name)))
    assert names == sorted([BATCH_NAME, f"{BATCH_NAME}（来自 {SOURCE_NAME}）"])


def test_attachment_owned_by_different_local_record_is_a_conflict(source, archive, tmp_path):
    target = open_target(source, TARGET)
    merchant, _, spent_on, invoice_no = INVOICED[0]
    with target.session_factory() as db:
        local = Expense(spent_on=spent_on, amount_cents=99999, merchant=merchant)
        db.add(local)
        db.flush()
        same_bytes = fake_pdf(tmp_path / "本地", "同一文件.pdf", f"发票{invoice_no}")
        store_file(db, target.settings, same_bytes, "同一文件.pdf", AttachmentKind.INVOICE, local)
        db.commit()

    report = merge(source, archive)

    conflicts = [i for i in report.section("records").items if i.action == "conflict"]
    assert len(conflicts) == 1 and "请人工核对" in conflicts[0].reason
    with target.session_factory() as db:
        rows = list(db.scalars(select(Expense).where(Expense.merchant == merchant)))
    assert [row.amount_cents for row in rows] == [99999]


def test_catalog_conflicts_keep_local_when_settings_not_included(source, archive):
    target = open_target(source, TARGET)
    with target.session_factory() as db:
        category = Category(name=f" {CUSTOM_CATEGORY} ", keywords=["本地关键词"])
        other = db.scalars(select(Category).order_by(Category.id)).first()
        db.add(category)
        db.flush()
        db.add(ChecklistRule(category_id=category.id, attachment_kind="contract", hint="本地提示"))
        db.add(MerchantMemory(seller_name="虚构文具行", category_id=other.id))
        db.commit()
        local_ids = (category.id, other.id)

    report = merge(source, archive, include_settings=False)

    with target.session_factory() as db:
        category = db.get(Category, local_ids[0])
        rules = list(
            db.scalars(select(ChecklistRule).where(ChecklistRule.category_id == category.id))
        )
        memory = db.get(MerchantMemory, "虚构文具行")
        custom = list(db.scalars(select(Category).where(Category.name.contains(CUSTOM_CATEGORY))))
        assert category.keywords == ["本地关键词"] and len(custom) == 1
        assert [rule.hint for rule in rules] == ["本地提示"]
        assert memory.category_id == local_ids[1]
    for key in ("categories", "rules", "memories"):
        assert report.section(key).conflicts == 1, key


def test_legacy_package_without_ledger_is_still_imported(source, archive, tmp_path):
    legacy = rewrite_archive(archive, tmp_path / "旧包.zip", drop=LEDGER_NAME)
    target = open_target(source, TARGET)

    report = merge(source, legacy)

    assert report.package["is_legacy"] is True
    assert report.package["tenant"] == SOURCE_NAME  # 来源名称退回清单里的账套名
    assert report.section("records").added == len(INVOICED) + 1
    assert any("旧版搬迁包" in warning for warning in report.warnings)
    assert digest_of(target).total_cents == sum(spec[1] for spec in INVOICED) + 1000


def _future_schema(manifest: dict) -> dict:
    return {**manifest, "schema_versions": {**manifest["schema_versions"], "rules_version": "999"}}


def test_package_from_newer_program_is_rejected(source, archive, tmp_path):
    newer = rewrite_archive(archive, tmp_path / "新版包.zip", manifest=_future_schema)
    target = open_target(source, TARGET)
    before = digest_of(target)

    for action in (merge_import, preview_merge):
        with pytest.raises(ImportRejectedError) as excinfo:
            action(source.state.tenants, source.state.control_session_factory, newer, TARGET)
        assert "请先升级程序" in excinfo.value.message
    assert digest_of(target) == before


def test_preview_writes_nothing(source, archive):
    target = open_target(source, TARGET)
    before = (digest_of(target), library_files(target.settings), accounts(source))

    report = preview_merge(
        source.state.tenants, source.state.control_session_factory, archive, TARGET
    )

    assert report.is_dry_run and report.section("records").added == len(INVOICED) + 1
    assert (digest_of(target), library_files(target.settings), accounts(source)) == before
    assert not (target.settings.data_dir / MERGE_STAGING_DIRNAME).exists()


def test_failure_midway_rolls_back_everything(source, archive, monkeypatch):
    target = open_target(source, TARGET)
    before = (digest_of(target), library_files(target.settings), accounts(source))
    real_place = merge_apply_records.place_file
    calls = []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 3:
            raise OSError("虚构磁盘故障")
        return real_place(*args, **kwargs)

    monkeypatch.setattr(merge_apply_records, "place_file", flaky)

    with pytest.raises(ImportFailedError) as excinfo:
        merge(source, archive)

    assert "已回滚" in excinfo.value.message and "虚构磁盘故障" not in excinfo.value.message
    assert (digest_of(target), library_files(target.settings), accounts(source)) == before


class _CommitFails(Session):
    def commit(self) -> None:
        raise RuntimeError("虚构提交失败")


def test_commit_failure_removes_placeholders_and_files(source, archive, monkeypatch):
    target = open_target(source, TARGET)
    before = (digest_of(target), library_files(target.settings), accounts(source))
    failing = dataclasses.replace(
        target, session_factory=sessionmaker(bind=target.engine, class_=_CommitFails)
    )
    monkeypatch.setattr(source.state.tenants, "get", lambda slug: failing)

    with pytest.raises(ImportFailedError):
        merge(source, archive)

    monkeypatch.undo()
    assert (digest_of(target), library_files(target.settings), accounts(source)) == before


def test_merge_into_missing_tenant_is_rejected(source, archive):
    with pytest.raises(ImportRejectedError) as excinfo:
        merge(source, archive, slug="nobody")

    assert excinfo.value.status_code == 404
    assert "replace" in excinfo.value.message


def test_engine_adapter_returns_serializable_reports(source, archive):
    open_target(source, TARGET)
    args = (source.state.tenants, source.state.control_session_factory, archive, TARGET)

    planned = engine.preview_import(*args, "merge")
    replaced = engine.preview_import(*args, "replace")
    done = engine.run_import(*args, "merge")

    json.dumps([planned, replaced, done], ensure_ascii=False)
    assert planned["is_dry_run"] is True and done["is_dry_run"] is False
    keys = {item["key"] for item in planned["items"]}
    assert keys >= {"records", "attachments", "users", "settings"}
    assert set(planned["items"][0]) == {
        "key", "label", "added", "updated", "skipped", "conflicts", "failed",
        "details", "truncated",
    }  # fmt: skip
    assert planned["include_settings"] is True
    assert replaced["mode"] == "replace" and replaced["target_exists"] is True
    with pytest.raises(ImportRejectedError):
        engine.run_import(*args, "upsert")


def test_deleted_source_record_is_not_imported(source, archive):
    target = open_target(source, TARGET)

    merge(source, archive)

    with target.session_factory() as db:
        spent = {row.spent_on for row in db.scalars(select(Expense))}
    assert date(2026, 9, 10) not in spent
