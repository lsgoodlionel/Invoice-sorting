# Duplex and Category PDFs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional duplex-safe print mode and category-specific print PDFs while retaining the existing combined PDF and ZIP layout.

**Architecture:** Extend the export request with a backward-compatible `duplex` flag. Refactor the PDF builder around record-level page appends so the same code can build one combined PDF and filtered category PDFs, then add all generated PDFs to the ZIP without changing original-material paths.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, pypdf, pytest, React 19, TypeScript, Mantine, Vitest.

---

### Task 1: Record-level duplex pagination

**Files:**
- Modify: `backend/src/invoice_sorting/exporter/print_pdf.py`
- Test: `backend/tests/unit/test_exporter_print_pdf.py`

- [ ] **Step 1: Write failing pagination tests**

Add tests that build one-page PDFs with `PdfWriter`, then assert that `duplex=True` produces page counts `2 + 2 + 1` for three one-page records, does not pad the last record, does not pad even records, and leaves current behavior unchanged when false:

```python
def one_page_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)
    with path.open("wb") as handle:
        writer.write(handle)


def test_duplex_pads_odd_records_except_last(tmp_path: Path):
    files = {}
    items = []
    for index in range(3):
        path = tmp_path / f"{index}.pdf"
        one_page_pdf(path)
        attachment = fake_attachment(index + 1, "application/pdf", path.name)
        files[index + 1] = path
        items.append(fake_item([attachment], seq=index + 1, expense_id=index + 1))
    result = build_print_pdf(items, lambda item: files[item.id], duplex=True)
    assert len(PdfReader(io.BytesIO(result.pdf_bytes)).pages) == 5


def test_duplex_false_keeps_three_pages(tmp_path: Path):
    # create the same three one-page records
    result = build_print_pdf(items, lambda item: files[item.id], duplex=False)
    assert len(PdfReader(io.BytesIO(result.pdf_bytes)).pages) == 3
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `cd backend && uv run pytest tests/unit/test_exporter_print_pdf.py -q`

Expected: FAIL because `build_print_pdf()` does not accept `duplex` and does not pad record boundaries.

- [ ] **Step 3: Implement record-level page counting**

Change the public signature and render each record into a temporary writer first. This is necessary because MIME type alone cannot tell whether a corrupt or missing file will actually contribute pages; padding must use successful record outputs:

```python
def build_print_pdf(
    items: list[PackageItem], resolve: PathResolver, *, duplex: bool = False
) -> PrintResult:
    skipped: dict[int, list[str]] = {}
    rendered: list[tuple[PackageItem, PdfWriter]] = []
    for item in items:
        record_writer = PdfWriter()
        for attachment in item.attachments:
            if _append_attachment(record_writer, attachment, resolve(attachment)):
                continue
            skipped.setdefault(item.expense.id, []).append(attachment.original_name)
        if record_writer.pages:
            rendered.append((item, record_writer))
    writer = PdfWriter()
    for index, (_item, record_writer) in enumerate(rendered):
        for page in record_writer.pages:
            writer.add_page(page)
        if duplex and len(record_writer.pages) % 2 == 1 and index < len(rendered) - 1:
            writer.add_blank_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)
    if len(writer.pages) == 0:
        writer.add_blank_page(width=A4_WIDTH_PT, height=A4_HEIGHT_PT)
    buffer = io.BytesIO()
    writer.write(buffer)
    return PrintResult(pdf_bytes=buffer.getvalue(), skipped=skipped)
```

Ensure the test also covers an unsupported-only middle record so it does not create a blank page.

- [ ] **Step 4: Run tests and commit**

Run: `cd backend && uv run pytest tests/unit/test_exporter_print_pdf.py -q`

Expected: all tests pass.

Commit:

```bash
git add backend/src/invoice_sorting/exporter/print_pdf.py backend/tests/unit/test_exporter_print_pdf.py
git commit -m "feat: 支持双面打印分页"
```

### Task 2: Category PDF naming and grouping

**Files:**
- Modify: `backend/src/invoice_sorting/exporter/naming.py`
- Test: `backend/tests/unit/test_exporter_print_pdf.py`

- [ ] **Step 1: Write failing category grouping tests**

Add assertions for stable grouping, configured category order, uncategorized last, and safe duplicate names:

```python
def test_category_print_groups_follow_package_order():
    first = SimpleNamespace(id=1, name="差旅/交通", sort=1)
    second = SimpleNamespace(id=2, name="办公费", sort=2)
    expenses = [
        SimpleNamespace(id=3, spent_on=date(2026, 11, 3), category=first, attachments=[]),
        SimpleNamespace(id=2, spent_on=date(2026, 11, 2), category=second, attachments=[]),
        SimpleNamespace(id=1, spent_on=date(2026, 11, 1), category=None, attachments=[]),
    ]
    items = package_items(expenses)
    groups = category_print_groups(items)
    assert [group.name for group in groups] == [
        "02_按分类打印/01_差旅_交通.pdf",
        "02_按分类打印/02_办公费.pdf",
        "02_按分类打印/03_未分类.pdf",
    ]
    assert [[item.expense.id for item in group.items] for group in groups] == [[3], [2], [1]]
```

- [ ] **Step 2: Run and verify failure**

Run: `cd backend && uv run pytest tests/unit/test_exporter_print_pdf.py::test_category_print_groups_follow_package_order -q`

Expected: FAIL because `category_print_groups` is undefined.

- [ ] **Step 3: Add a focused grouping value object**

Add to `naming.py`:

```python
CATEGORY_PRINT_DIR = "02_按分类打印"

@dataclass(frozen=True)
class CategoryPrintGroup:
    name: str
    items: tuple[PackageItem, ...]


def category_print_groups(items: list[PackageItem]) -> list[CategoryPrintGroup]:
    grouped: dict[tuple[int, str], list[PackageItem]] = {}
    for item in items:
        category = item.expense.category
        key = (category.id if category else -1, category_token(item.expense))
        grouped.setdefault(key, []).append(item)
    used: set[str] = set()
    result = []
    for index, grouped_items in enumerate(grouped.values(), start=1):
        token = category_token(grouped_items[0].expense)
        filename = unique_name(f"{CATEGORY_PRINT_DIR}/{index:02d}_{token}.pdf", used)
        result.append(CategoryPrintGroup(filename, tuple(grouped_items)))
    return result
```

Use insertion order because `items` is already category/date ordered.

- [ ] **Step 4: Run tests and commit**

Run: `cd backend && uv run pytest tests/unit/test_exporter_print_pdf.py -q`

Commit:

```bash
git add backend/src/invoice_sorting/exporter/naming.py backend/tests/unit/test_exporter_print_pdf.py
git commit -m "feat: 增加分类打印分组"
```

### Task 3: Export API and ZIP members

**Files:**
- Modify: `backend/src/invoice_sorting/batches/schemas.py`
- Modify: `backend/src/invoice_sorting/batches/router.py`
- Modify: `backend/src/invoice_sorting/exporter/package.py`
- Test: `backend/tests/integration/test_exporter_api.py`

- [ ] **Step 1: Write failing API/ZIP tests**

Extend the test helper to accept `duplex` and add assertions that every export contains the combined PDF plus category PDFs, category contents have expected page counts, and omitted `duplex` preserves old page count:

```python
def export(client, batch_id: int, layout: str = "by_expense", duplex: bool | None = None):
    body = {"layout": layout}
    if duplex is not None:
        body["duplex"] = duplex
    response = client.post(f"/api/batches/{batch_id}/export", json=body)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_export_adds_category_pdfs_and_duplex_padding(client):
    # create categorized one-page records and one uncategorized record
    archive = download(client, export(client, batch_id, duplex=True))
    names = archive.namelist()
    assert "01_打印版_全部材料.pdf" in names
    assert [name for name in names if name.startswith("02_按分类打印/")] == expected_names
    assert len(PdfReader(io.BytesIO(archive.read("01_打印版_全部材料.pdf"))).pages) == expected_pages
```

- [ ] **Step 2: Run and verify failure**

Run: `cd backend && uv run pytest tests/integration/test_exporter_api.py -q`

Expected: FAIL because `duplex` is forbidden and category members do not exist.

- [ ] **Step 3: Thread the flag through and generate all print members**

Add `duplex: bool = False` to `ExportRequest`, pass `body.duplex` from the router, and change `export_batch(..., duplex: bool = False)`. Build members as follows:

```python
printed = build_print_pdf(items, resolve, duplex=duplex)
members = {SUMMARY_NAME: workbook, PRINT_NAME: printed.pdf_bytes}
for group in category_print_groups(items):
    members[group.name] = build_print_pdf(list(group.items), resolve, duplex=duplex).pdf_bytes
```

The workbook must continue using the combined result’s `notes_for` so skipped-file notes are not duplicated or lost.

- [ ] **Step 4: Run tests and commit**

Run: `cd backend && uv run pytest tests/unit/test_exporter_print_pdf.py tests/integration/test_exporter_api.py -q`

Commit:

```bash
git add backend/src/invoice_sorting/batches backend/src/invoice_sorting/exporter backend/tests/unit/test_exporter_print_pdf.py backend/tests/integration/test_exporter_api.py
git commit -m "feat: 资料包生成分类打印 PDF"
```

### Task 4: Frontend duplex control

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/hooks/batches.ts`
- Modify: `frontend/src/components/batches/ExportSection.tsx`
- Test: `frontend/src/components/batches/ExportSection.test.tsx`

- [ ] **Step 1: Write the failing interaction test**

```tsx
test('exports with the duplex option', async () => {
  const user = userEvent.setup();
  const { calls } = mockFetch({ 'POST /api/batches/1/export': record });
  renderWithProviders(<ExportSection batch={makeBatch({ id: 1, item_count: 1, expenses: [makeExpense()] })} />);
  expect(screen.getByRole('checkbox', { name: '适合双面打印' })).not.toBeChecked();
  await user.click(screen.getByRole('checkbox', { name: '适合双面打印' }));
  await user.click(screen.getByRole('button', { name: '生成资料包' }));
  await waitFor(() => expect(JSON.parse(calls[0].body as string)).toEqual({ layout: 'by_expense', duplex: true }));
});
```

- [ ] **Step 2: Run and verify failure**

Run: `cd frontend && pnpm test -- src/components/batches/ExportSection.test.tsx`

Expected: FAIL because the checkbox is absent.

- [ ] **Step 3: Implement typed export options and the control**

Add:

```ts
export interface BatchExportOptions { layout: ExportLayout; duplex: boolean }
```

Change `exportZip` and `useExportBatch` to accept `BatchExportOptions`. In `ExportSection`, add `const [duplex, setDuplex] = useState(false)`, render a Mantine `Checkbox` labeled “适合双面打印”, and call:

```tsx
onClick={() => exportBatch.mutate({ layout, duplex })}
```

Update the hint to explain that odd-page records except the last get an A4 blank page and that the ZIP also contains category PDFs.

- [ ] **Step 4: Run tests, type-check, and commit**

Run:

```bash
cd frontend && pnpm test -- src/components/batches/ExportSection.test.tsx
cd frontend && pnpm lint
```

Expected: tests and TypeScript pass.

Commit:

```bash
git add frontend/src/api frontend/src/components/batches/ExportSection.tsx frontend/src/components/batches/ExportSection.test.tsx
git commit -m "feat: 增加双面打印导出选项"
```

### Task 5: Export documentation and regression verification

**Files:**
- Modify: `README.md`
- Modify: `docs/api-contract.md`

- [ ] **Step 1: Document the request and ZIP structure**

Document `POST /api/batches/{id}/export` body as `{ "layout": "by_expense", "duplex": false }`, state the default, explain the padding boundary, and list `02_按分类打印/*.pdf`.

- [ ] **Step 2: Run the complete relevant checks**

Run:

```bash
cd backend && uv run pytest tests/unit/test_exporter_print_pdf.py tests/integration/test_exporter_api.py -q
cd backend && uv run ruff check src tests
cd frontend && pnpm test -- src/components/batches/ExportSection.test.tsx
cd frontend && pnpm lint
```

Expected: all commands exit 0.

- [ ] **Step 3: Commit the documented, independently working exporter**

```bash
git add README.md docs/api-contract.md
git commit -m "docs: 说明双面与分类资料包"
```

Do not release yet; continue with the Apple Gmail import plan so one version contains all user-approved changes.
