# Rail Ticket Lodging Link Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parse split-line station layouts from railway e-invoices so the existing lodging matcher can automatically attach a unique matching ticket and satisfy the transport checklist.

**Architecture:** Add a narrowly scoped fallback route regex to `RailTicketParser` after the existing standard pattern. Keep the normalized travel-details contract unchanged so existing L7 grouping, lodging scoring, auto-confirm, amount merge, and checklist logic continue to work without a second matcher.

**Tech Stack:** Python 3.12, regex-based PDF text parsing, SQLAlchemy importer, pytest.

---

### Task 1: Parse split-line station layouts

**Files:**
- Modify: `backend/src/invoice_sorting/parsers/rail_ticket.py`
- Modify: `backend/tests/unit/test_parsers.py`

- [ ] **Step 1: Write a failing parser test**

Call `RailTicketParser.parse()` with privacy-safe synthetic text matching the supplied layout and assert:

```python
assert parsed.item_summary == "安吉-上海南 C3029"
assert parsed.travel == {
    "date": "2026-09-06",
    "from": "安吉",
    "to": "上海南",
    "passenger": "李欣",
    "train_or_flight": "C3029",
}
```

- [ ] **Step 2: Run and verify failure**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_parsers.py -k rail_ticket -q`

Expected: the new test fails with empty route and train fields.

- [ ] **Step 3: Implement a fallback route extractor**

Keep `ROUTE_RE` first. Add a multiline fallback that requires a route line with two Chinese names and a legal train number, followed by a line containing two station markers. Return the same three groups as the standard route pattern and use it only inside `RailTicketParser`.

- [ ] **Step 4: Run tests and commit**

Run: `cd backend && .venv/bin/python -m pytest tests/unit/test_parsers.py tests/unit/test_parsers_travel.py tests/unit/test_evidence_details.py -q`

Commit:

```bash
git add backend/src/invoice_sorting/parsers/rail_ticket.py backend/tests/unit/test_parsers.py
git commit -m "fix: 识别分行站名铁路电子客票"
```

### Task 2: Verify unique lodging attachment and ambiguity safety

**Files:**
- Modify: `backend/tests/integration/test_lodging_grouping.py`
- Modify: `backend/tests/unit/test_importer_lodging.py`

- [ ] **Step 1: Add regression assertions for parsed sample details**

Use the parsed details to build an `EvidenceItem` and assert `transport_fits()` succeeds for a Shanghai stay covering 2026-09-06, but fails for another city or an out-of-window date.

- [ ] **Step 2: Add an ambiguity integration test**

Create two eligible Shanghai lodging records with the same stay window, import the parsed train ticket, and assert no automatic attachment occurs while both records appear as candidates. Retain the existing unique-candidate test that asserts automatic attachment and checklist satisfaction.

- [ ] **Step 3: Run lodging regression tests**

Run:

```bash
cd backend && .venv/bin/python -m pytest tests/unit/test_importer_lodging.py tests/integration/test_lodging_grouping.py tests/integration/test_lodging_amounts.py -q
```

Expected: unique match attaches, ambiguous match remains for confirmation, mismatched city/date does not link, and all existing lodging tests pass.

- [ ] **Step 4: Validate the real sample locally and commit tests**

Run the parser against `/Users/lionel/Develop/26339119363000147798-电子发票.pdf` without copying it into the repository. Confirm route `安吉-上海南`, number `C3029`, date `2026-09-06`, and `vehicle=train` after `travel_details()`.

Commit:

```bash
git add backend/tests/unit/test_importer_lodging.py backend/tests/integration/test_lodging_grouping.py
git commit -m "test: 覆盖铁路票住宿关联边界"
```

### Task 3: Document and verify the completed optimization

**Files:**
- Modify: `README.md`
- Modify: `docs/凭证识别与自动归并_设计_v2.1.md`
- Modify: `docs/差旅住宿凭证_设计.md`

- [ ] **Step 1: Document the supported layout and matching boundary**

State that split-line station railway e-invoices are supported, and explain unique auto-attach, ambiguous recommendation-only, date window, and city endpoint requirements.

- [ ] **Step 2: Run focused checks**

```bash
cd backend && .venv/bin/python -m pytest tests/unit/test_parsers.py tests/unit/test_parsers_travel.py tests/unit/test_importer_lodging.py tests/integration/test_lodging_grouping.py tests/integration/test_lodging_amounts.py -q
cd backend && .venv/bin/python -m ruff check src tests
```

- [ ] **Step 3: Commit documentation**

```bash
git add README.md docs/凭证识别与自动归并_设计_v2.1.md docs/差旅住宿凭证_设计.md
git commit -m "docs: 说明铁路票住宿自动关联"
```

Do not release yet; first complete the separately designed cross-currency order/payment matching improvement, then publish all approved changes together as `v0.3.0`.
