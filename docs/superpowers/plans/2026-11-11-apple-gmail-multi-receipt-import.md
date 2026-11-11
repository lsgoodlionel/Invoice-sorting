# Apple Gmail Multi-Receipt Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import a Gmail-printed Apple purchase thread as one traceable source document and one independent expense candidate per Apple Order ID, then publish the completed exporter and importer changes as v0.3.0.

**Architecture:** Add an isolated Apple Gmail splitter that returns receipt page ranges and extracted text, persist the original PDF in a source-document table, and import generated child PDFs through the existing attachment recognition/grouping flow. Refactor one-file outcomes to carry multiple imported entries while preserving the current upload response shape and session finish behavior.

**Tech Stack:** Python 3.12, SQLAlchemy, SQLite additive migrations, pypdf, FastAPI, pytest, Docker, GitHub Actions/Releases.

---

### Task 1: Characterize the real Apple sample and splitter contract

**Files:**
- Create: `backend/src/invoice_sorting/evidence/composite.py`
- Create: `backend/tests/unit/test_apple_gmail_splitter.py`
- Test fixture source: `/Users/lionel/Develop/Gmail - Your purchases from Apple.pdf`

- [ ] **Step 1: Build a privacy-safe structural fixture in the test**

Create a deterministic synthetic PDF in the test with ReportLab containing three receipts, including one two-page receipt. Use invented Order IDs, document numbers and product names. Do not copy or commit personal email addresses, payment identifiers, purchase details, or unrelated Gmail content from the supplied sample. Reserve the real sample for the final local end-to-end verification only.

- [ ] **Step 2: Write failing splitter tests**

Define the contract:

```python
@dataclass(frozen=True)
class CompositePart:
    order_no: str
    start_page: int  # one-based, inclusive
    end_page: int    # one-based, inclusive
    text: str


def split_apple_gmail_pdf(path: Path) -> list[CompositePart]:
    """Return safe, ordered Apple receipt ranges; return an empty list for non-matches."""
    raise NotImplementedError
```

Tests must assert unique Order IDs, ascending non-overlapping ranges, complete cross-page text, `[]` for ordinary PDFs, and a domain error for two receipt starts on the same physical page.

- [ ] **Step 3: Run and verify failure**

Run: `cd backend && uv run pytest tests/unit/test_apple_gmail_splitter.py -q`

Expected: FAIL because the module is absent.

- [ ] **Step 4: Implement text-only detection and safe page ranges**

Use `PdfReader`, normalize non-breaking spaces, detect Gmail/Apple thread markers, and compile anchored patterns:

```python
ORDER_ID = re.compile(r"(?im)^\s*Order ID\s*[:：]?\s*([A-Z0-9-]+)\s*$")
RECEIPT = re.compile(r"(?im)^\s*Receipt\s*$")

def split_apple_gmail_pdf(path: Path) -> list[CompositePart]:
    reader = PdfReader(path)
    page_texts = [(page.extract_text() or "").replace("\xa0", " ") for page in reader.pages]
    joined = "\n".join(page_texts)
    if "Your purchases from Apple" not in joined or "Order ID" not in joined:
        return []
    starts = _receipt_starts(page_texts)
    _require_one_start_per_page(starts)
    return _parts_from_starts(page_texts, starts)
```

Keep helper functions private and deterministic; raise `CompositeSplitError` with a Chinese message when boundaries are ambiguous.

- [ ] **Step 5: Run tests and commit**

Run: `cd backend && uv run pytest tests/unit/test_apple_gmail_splitter.py -q`

Commit:

```bash
git add backend/src/invoice_sorting/evidence/composite.py backend/tests/unit/test_apple_gmail_splitter.py backend/tests/fixtures/evidence
git commit -m "feat: 识别 Apple 邮件多回执边界"
```

### Task 2: Correct Apple receipt field extraction

**Files:**
- Modify: `backend/src/invoice_sorting/evidence/recognizers/app_store.py`
- Test: `backend/tests/unit/test_evidence_recognizers.py`

- [ ] **Step 1: Write failing receipt-block tests**

Use text where a Gmail timestamp precedes `Receipt October 30, 2026` and assert:

```python
assert result.occurred_on == date(2026, 10, 30)
assert result.amount_cents == 10000
assert result.currency == "USD"
assert result.item_name == "ChatGPT Pro 100 (Monthly)"
assert result.order_no == "MSHQ92HTXH"
assert result.details == {"document_no": "654211965027"}
```

- [ ] **Step 2: Run and verify the date/details failures**

Run: `cd backend && uv run pytest tests/unit/test_evidence_recognizers.py -q`

- [ ] **Step 3: Add receipt-scoped parsing and populate existing structured details**

Use the existing `RecognizedEvidence.details` field and update the Apple recognizer to prefer a date adjacent to the `Receipt` heading before any generic date fallback. Extract `Document No.` into details; the existing `apply_evidence()` already persists that mapping.

Core precedence:

```python
receipt_date = value_after(doc, r"Receipt")
occurred_on = parse_date(receipt_date) or parse_date(value_below(doc, ORDER_DATE_LABEL))
details = {"document_no": document_no} if document_no else {}
```

- [ ] **Step 4: Run tests and commit**

Run: `cd backend && uv run pytest tests/unit/test_evidence_recognizers.py tests/unit/test_evidence_service.py -q`

Commit:

```bash
git add backend/src/invoice_sorting/evidence/recognizers/app_store.py backend/tests/unit/test_evidence_recognizers.py
git commit -m "fix: 准确识别 Apple 回执字段"
```

### Task 3: Persist source documents and child provenance

**Files:**
- Modify: `backend/src/invoice_sorting/db/models.py`
- Create: `backend/src/invoice_sorting/attachments/sources.py`
- Modify: `backend/src/invoice_sorting/attachments/serializers.py`
- Modify: `backend/tests/unit/test_db_migrate.py`
- Modify: `backend/tests/integration/test_attachments_api.py`

- [ ] **Step 1: Write failing additive-migration and serialization tests**

Assert that an existing SQLite database gains a `source_document` table and nullable attachment columns `source_document_id`, `source_page_start`, `source_page_end`, and `source_splitter`. Assert serialized attachments expose:

```json
{"source": {"id": 1, "original_name": "Gmail - Your purchases from Apple.pdf", "page_start": 1, "page_end": 2}}
```

- [ ] **Step 2: Run and verify failure**

Run: `cd backend && uv run pytest tests/unit/test_db_migrate.py tests/integration/test_attachments_api.py -q`

- [ ] **Step 3: Add the source model and nullable child columns**

Add `SourceDocument` with `id`, unique `sha256`, `file_path`, `original_name`, `mime`, `size`, and `created_at`. Add nullable columns and relationships to `Attachment`. Keep all new attachment columns nullable so `add_missing_columns()` can safely upgrade existing SQLite databases.

Add focused storage functions:

```python
def store_source_document(session: Session, settings: Settings, src: Path, name: str) -> SourceDocument:
    digest = sha256_of(src)
    existing = session.scalar(select(SourceDocument).where(SourceDocument.sha256 == digest))
    if existing:
        raise DuplicateSourceError(existing)
    destination = settings.data_dir / "导入来源" / f"{digest}.pdf"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, destination)
    source = SourceDocument(sha256=digest, file_path=destination.relative_to(settings.data_dir).as_posix(), original_name=name, mime="application/pdf", size=destination.stat().st_size)
    session.add(source)
    session.flush()
    return source
```

Add cleanup-on-rollback support and a `source_absolute_path()` helper.

- [ ] **Step 4: Run tests and commit**

Run: `cd backend && uv run pytest tests/unit/test_db_migrate.py tests/integration/test_attachments_api.py -q`

Commit:

```bash
git add backend/src/invoice_sorting/db/models.py backend/src/invoice_sorting/attachments backend/tests/unit/test_db_migrate.py backend/tests/integration/test_attachments_api.py
git commit -m "feat: 保存复合凭证来源追溯"
```

### Task 4: Generate child PDFs and import multiple outcomes atomically

**Files:**
- Create: `backend/src/invoice_sorting/importer/composite.py`
- Modify: `backend/src/invoice_sorting/importer/service.py`
- Modify: `backend/src/invoice_sorting/importer/file_import.py`
- Modify: `backend/src/invoice_sorting/importer/router.py`
- Modify: `backend/src/invoice_sorting/importer/sessions.py`
- Test: `backend/tests/integration/test_apple_gmail_import.py`

- [ ] **Step 1: Write a failing end-to-end import test**

Upload a three-receipt fixture to `/api/imports/{session_id}/files`, finish the session, and assert:

- upload response is `imported`, with message “已拆分 3 张 Apple 回执”；
- finish returns three groups with distinct attachment IDs and Order IDs;
- each attachment points to one source document and the correct page range;
- importing the same original again returns duplicate;
- one malformed child creates a notice/error but valid children remain available.

- [ ] **Step 2: Run and verify failure**

Run: `cd backend && uv run pytest tests/integration/test_apple_gmail_import.py -q`

- [ ] **Step 3: Implement child PDF generation**

In `importer/composite.py`, write selected pages with `PdfWriter`:

```python
@dataclass(frozen=True)
class PreparedChild:
    path: Path
    name: str
    source: SourceDocument
    part: CompositePart


def prepare_apple_children(src: Path, source: SourceDocument, parts: list[CompositePart], temp: Path) -> list[PreparedChild]:
    reader = PdfReader(src)
    children = []
    for part in parts:
        writer = PdfWriter()
        for page_index in range(part.start_page - 1, part.end_page):
            writer.add_page(reader.pages[page_index])
        path = temp / f"Apple_{part.order_no}.pdf"
        with path.open("wb") as handle:
            writer.write(handle)
        children.append(PreparedChild(path, path.name, source, part))
    return children
```

- [ ] **Step 4: Refactor `FileOutcome` for multiple entries without breaking callers**

Replace singular storage with `entries: tuple[tuple[Attachment, EvidenceItem], ...]`, add compatibility properties `attachment` and `item` returning the first entry, and update `ImportResult.add_outcome`, `record_outcome`, and `serialize_file_outcome` to record all attachment IDs while returning the first attachment plus a split-count message to the upload row.

The normal one-file path constructs a one-entry tuple. The composite path stores the source, creates/imports each child, sets provenance columns, and commits source plus children in one transaction. On database failure, roll back and remove every copied source/child path.

- [ ] **Step 5: Run tests and commit**

Run: `cd backend && uv run pytest tests/integration/test_apple_gmail_import.py tests/integration/test_import_files_concurrency.py tests/integration/test_import_groups_api.py -q`

Commit:

```bash
git add backend/src/invoice_sorting/importer backend/tests/integration/test_apple_gmail_import.py
git commit -m "feat: 导入 Apple 邮件多张回执"
```

### Task 5: Checklist, attribution, and duplicate behavior

**Files:**
- Modify: `backend/src/invoice_sorting/importer/group_summary.py`
- Modify: `backend/src/invoice_sorting/importer/suggestions.py`
- Modify: `backend/src/invoice_sorting/importer/confirm.py`
- Test: `backend/tests/integration/test_apple_gmail_import.py`
- Test: `backend/tests/integration/test_import_confirm_groups.py`

- [ ] **Step 1: Extend the failing integration test through confirmation**

For each returned Apple group, submit `action=create` with USD original amount and CNY reimbursement amount. Assert three expenses are created independently, each attachment belongs to exactly one expense, source metadata remains shared, `invoice_exempt` and `is_online` are true, checklist items are generated, and learned Apple/item category suggestions are respected.

- [ ] **Step 2: Run and verify any missing business defaults**

Run: `cd backend && uv run pytest tests/integration/test_apple_gmail_import.py tests/integration/test_import_confirm_groups.py -q`

- [ ] **Step 3: Add only the minimal Apple defaults needed by existing flows**

Ensure group summary carries `currency="USD"`, `original_amount_cents`, merchant `Apple`, item summary, `is_online=True`, and `invoice_exempt=True` for foreign Apple orders. Do not perform exchange-rate conversion. Use the existing category-memory lookup before keyword suggestions and leave `category_id=None` when neither matches.

- [ ] **Step 4: Run tests and commit**

Run: `cd backend && uv run pytest tests/integration/test_apple_gmail_import.py tests/integration/test_import_confirm_groups.py tests/unit/test_importer_grouping.py -q`

Commit:

```bash
git add backend/src/invoice_sorting/importer backend/tests/integration/test_apple_gmail_import.py backend/tests/integration/test_import_confirm_groups.py
git commit -m "feat: 完成 Apple 回执清单与归属"
```

### Task 6: Documentation, version, and full validation

**Files:**
- Modify: `README.md`
- Modify: `docs/api-contract.md`
- Modify: `docs/凭证识别与自动归并_设计_v2.1.md`
- Modify: `docs/部署与运维.md`
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`

- [ ] **Step 1: Document supported format and traceability**

Document Apple Gmail multi-receipt detection, one Order ID per candidate, source-page provenance, duplicate behavior, unsupported image-only/ambiguous documents, USD handling, and the unchanged manual confirmation boundary.

- [ ] **Step 2: Update version to 0.3.0 and synchronize the lock**

Change `backend/pyproject.toml` to `version = "0.3.0"`, run `cd backend && uv lock`, and update README installation examples/current release to `v0.3.0` only immediately before release.

- [ ] **Step 3: Run the full repository checks**

Run:

```bash
cd backend && uv run pytest -q
cd backend && uv run ruff check src tests
cd frontend && pnpm test
cd frontend && pnpm lint
cd frontend && pnpm build
docker compose -f deploy/docker/docker-compose.yml build
docker compose -f deploy/docker/docker-compose.yml up -d
curl -fsS http://127.0.0.1:8000/api/health
```

Expected: all tests/checks/builds pass, containers are healthy, and the real authorized sample completes upload → split → finish → confirm → package export in an isolated test ledger.

- [ ] **Step 4: Commit release-ready code and docs**

```bash
git add README.md docs backend/pyproject.toml backend/uv.lock
git commit -m "chore: 准备 v0.3.0 发布"
```

### Task 7: GitHub, CI, Obsidian, and Release closure

**Files:**
- Read: `/Users/lionel/.codex/memories/claude-code-migration/github-repositories.md`
- Modify: existing Obsidian project overview/progress file for Invoice Sorting

- [ ] **Step 1: Verify registered remote, branch, and pre-push state**

Run:

```bash
git status --short --branch
git remote -v
git log --oneline --decorate -10
```

Confirm the memory registry points to `lsgoodlionel/Invoice-sorting`, current branch is `main`, no unrelated changes are staged, and all required checks are recorded in Obsidian as pre-push evidence.

- [ ] **Step 2: Push normal commits and monitor CI**

Run `git push origin main`, then use GitHub CLI/API to identify the checks for the pushed commit. Record each as passed, failed, skipped, not triggered, or in progress; do not call in-progress checks passed.

- [ ] **Step 3: Stop on failed CI; otherwise tag v0.3.0**

After CI passes and `backend/pyproject.toml` reports `0.3.0`:

```bash
git tag v0.3.0
git push origin v0.3.0
```

Monitor `.github/workflows/release.yml` until completion and verify the GitHub Release exists with expected assets and checksums.

- [ ] **Step 4: Update Obsidian with final evidence**

Record date, branch, pushed commit, tag, test/Docker evidence, CI links and conclusions, Release URL, delivered behavior, remaining limitations (image-only/ambiguous Gmail PDFs), and next step. Do not write credentials or sensitive purchase details.

- [ ] **Step 5: Final clean-state verification**

Run:

```bash
git status --short --branch
git describe --tags --always
```

Expected: clean `main` aligned with `origin/main`, description `v0.3.0`, GitHub Release published, and Obsidian synchronized.
