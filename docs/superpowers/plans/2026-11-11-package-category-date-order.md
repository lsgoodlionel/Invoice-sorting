# 资料包按分类和日期排序 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让批次资料包中的全部记录按分类配置顺序排列，并在同一分类内按消费日期和记录 ID 稳定排序。

**Architecture:** 只在 `package_items()` 这个统一编号入口定义排序规则，使汇总表、打印版 PDF、发票原件和两种支撑材料布局继续共享同一份 `PackageItem` 列表。测试分为纯排序单元测试和“按材料类型分组”导出 API 回归测试，既验证边界规则，也验证最终 ZIP 中的序号一致性。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy、pytest、openpyxl、zipfile

---

## 文件结构

- `backend/src/invoice_sorting/exporter/naming.py`：资料包记录与附件的统一排序、编号和命名规则；本次只调整记录排序键。
- `backend/tests/unit/test_exporter_print_pdf.py`：现有命名与打印排序单元测试；新增分类优先、分类内日期、同日 ID、未分类置后的精确回归测试。
- `backend/tests/integration/test_exporter_api.py`：现有资料包导出端到端测试；新增按材料类型分组时汇总表、发票原件和支撑材料共用新序号的测试。
- `README.md`：在现有“生成资料包”说明中补充默认排序规则。

### Task 1: 用失败测试锁定统一排序行为

**Files:**
- Modify: `backend/tests/unit/test_exporter_print_pdf.py:99-119`
- Modify: `backend/tests/integration/test_exporter_api.py:119-125`

- [ ] **Step 1: 增加纯排序单元测试，并给旧测试对象补上 `category=None`**

在 `test_naming_helpers()` 的三个旧测试对象中增加 `category=None`，保持旧测试与真实 `Expense` 接口一致：

```python
expenses = [
    SimpleNamespace(id=2, spent_on=date(2026, 9, 2), category=None, attachments=[]),
    SimpleNamespace(id=3, spent_on=date(2026, 9, 1), category=None, attachments=[]),
    SimpleNamespace(id=1, spent_on=date(2026, 9, 2), category=None, attachments=[]),
]
```

随后新增独立测试：

```python
def test_package_items_sort_by_category_then_date_and_put_uncategorized_last():
    first = SimpleNamespace(id=10, sort=1)
    second = SimpleNamespace(id=20, sort=2)
    expenses = [
        SimpleNamespace(id=5, spent_on=date(2026, 8, 1), category=second, attachments=[]),
        SimpleNamespace(id=4, spent_on=date(2026, 9, 2), category=first, attachments=[]),
        SimpleNamespace(id=3, spent_on=date(2026, 9, 1), category=first, attachments=[]),
        SimpleNamespace(id=2, spent_on=date(2026, 9, 1), category=first, attachments=[]),
        SimpleNamespace(id=1, spent_on=date(2026, 7, 1), category=None, attachments=[]),
    ]

    assert [(item.seq, item.expense.id) for item in package_items(expenses)] == [
        (1, 2),
        (2, 3),
        (3, 4),
        (4, 5),
        (5, 1),
    ]
```

- [ ] **Step 2: 增加按材料类型分组的 API 回归测试**

在 `test_export_by_kind_layout()` 后新增：

```python
def test_export_by_kind_uses_category_then_date_order_for_every_member(client):
    categories = client.get("/api/categories").json()["data"][:2]
    first, second = categories
    expenses = [
        make_expense(
            client,
            spent_on="2026-09-03",
            merchant="前分类晚日期",
            category_id=first["id"],
        ),
        make_expense(
            client,
            spent_on="2026-09-01",
            merchant="前分类早日期",
            category_id=first["id"],
        ),
        make_expense(
            client,
            spent_on="2026-08-01",
            merchant="后分类更早日期",
            category_id=second["id"],
        ),
        make_expense(client, spent_on="2026-07-01", merchant="未分类最早日期"),
    ]
    for expense in expenses:
        upload(client, expense["id"], [("订单.png", png_bytes())], kind="order")
    batch = make_batch(client, "分类排序批次")
    add_items(client, batch["id"], [expense["id"] for expense in expenses], force=True)

    archive = download(client, export(client, batch["id"], "by_kind"))
    summary, _ = summary_rows(archive)
    body = summary[2:-1]
    expected_merchants = ["前分类早日期", "前分类晚日期", "后分类更早日期", "未分类最早日期"]
    assert [row[2] for row in body] == expected_merchants

    invoice_merchants = [
        Path(name).stem.split("_")[3]
        for name in sorted(
            name for name in archive.namelist() if name.startswith("02_发票原件/")
        )
    ]
    assert invoice_merchants == expected_merchants

    order_members = sorted(
        name
        for name in archive.namelist()
        if name.startswith("03_支撑材料/订单明细/")
    )
    assert [Path(name).stem.split("_")[1] for name in order_members] == expected_merchants
```

- [ ] **Step 3: 运行两个新测试并确认因旧排序规则失败**

Run:

```bash
cd backend
.venv/bin/pytest -q \
  tests/unit/test_exporter_print_pdf.py::test_package_items_sort_by_category_then_date_and_put_uncategorized_last \
  tests/integration/test_exporter_api.py::test_export_by_kind_uses_category_then_date_order_for_every_member
```

Expected: 两个测试均失败；实际顺序仍以全局消费日期为先，单元测试首先出现 ID `1`，API 测试首先出现商家“未分类最早日期”。

### Task 2: 在统一入口实现最小排序改动

**Files:**
- Modify: `backend/src/invoice_sorting/exporter/naming.py:59-65`
- Test: `backend/tests/unit/test_exporter_print_pdf.py`
- Test: `backend/tests/integration/test_exporter_api.py`

- [ ] **Step 1: 增加排序键函数并让 `package_items()` 使用它**

在 `ordered_attachments()` 和 `package_items()` 之间加入：

```python
def package_item_sort_key(expense: Expense) -> tuple[object, ...]:
    """已分类按配置顺序在前；分类内按消费日期和记录 id 稳定排序。"""
    category = expense.category
    category_key = (1, 0, 0) if category is None else (0, category.sort, category.id)
    return (*category_key, expense.spent_on, expense.id)
```

然后将 `package_items()` 改为：

```python
def package_items(expenses: list[Expense]) -> list[PackageItem]:
    """按分类配置顺序、消费日期和 id 编号，未分类置后，序号从 1 开始。"""
    ordered = sorted(expenses, key=package_item_sort_key)
    return [
        PackageItem(seq=index, expense=expense, attachments=ordered_attachments(expense))
        for index, expense in enumerate(ordered, start=1)
    ]
```

- [ ] **Step 2: 重跑两个新测试并确认转绿**

Run:

```bash
cd backend
.venv/bin/pytest -q \
  tests/unit/test_exporter_print_pdf.py::test_package_items_sort_by_category_then_date_and_put_uncategorized_last \
  tests/integration/test_exporter_api.py::test_export_by_kind_uses_category_then_date_order_for_every_member
```

Expected: `2 passed`。

- [ ] **Step 3: 运行资料包相关测试，确认没有破坏附件顺序、命名和导出结构**

Run:

```bash
cd backend
.venv/bin/pytest -q tests/unit/test_exporter_print_pdf.py tests/integration/test_exporter_api.py
```

Expected: 全部通过，无失败。

- [ ] **Step 4: 提交排序实现与回归测试**

```bash
git add backend/src/invoice_sorting/exporter/naming.py
git add backend/tests/unit/test_exporter_print_pdf.py
git add backend/tests/integration/test_exporter_api.py
git commit -m "feat: 资料包按分类和日期排序"
```

### Task 3: 更新说明并完成验证闭环

**Files:**
- Modify: `README.md:226`

- [ ] **Step 1: 在现有资料包说明中记录新默认顺序**

在“生成资料包”段落的“序号贯穿三者”后补充：

```markdown
全部记录默认按设置中的分类顺序排列，同一分类内按消费日期升序排列，未分类排在最后；汇总表、打印版和各材料目录使用相同序号。
```

- [ ] **Step 2: 运行格式检查和后端单元测试**

Run:

```bash
git diff --check
cd backend
.venv/bin/pytest -q tests/unit --maxfail=1
```

Expected: `git diff --check` 无输出；后端单元测试全部通过。允许项目已有的第三方 deprecation warnings，但不允许失败。

- [ ] **Step 3: 再次运行资料包 API 集成测试作为最终用户流程验证**

Run:

```bash
cd backend
.venv/bin/pytest -q tests/integration/test_exporter_api.py
```

Expected: 全部通过，无失败；不运行已知会触发 macOS watchdog FSEvents 原生崩溃的完整 integration 套件。

- [ ] **Step 4: 提交 README 与实施计划**

```bash
git add README.md
git add docs/superpowers/plans/2026-11-11-package-category-date-order.md
git commit -m "docs: 说明资料包默认排序"
```

- [ ] **Step 5: 核对仓库、分支和待推送提交**

Run:

```bash
git remote -v
git status --short --branch
git log --oneline origin/main..HEAD
```

Expected: `origin` 为 `https://github.com/lsgoodlionel/Invoice-sorting.git`，分支为 `main`，工作区干净，只包含本任务的规格、实现和文档提交。

- [ ] **Step 6: 普通推送并核对 GitHub CI/CD 状态**

Run:

```bash
git push origin main
```

Expected: 非 force push 成功。随后查询本次提交关联的 GitHub Actions；如未触发、进行中、通过或失败，按实际状态记录，不把排队或运行中写成通过。

- [ ] **Step 7: 更新现有 Obsidian 项目进度记录**

在 `/Users/lionel/Library/Favorites/AI/claude/10-项目/发票账本与报销管理（Invoice Sorting）` 的现有“项目总览”或“进度与路线图”中追加 2026-11-11 记录，包括：分支 `main`、实际推送提交、测试命令与结果、GitHub CI/CD 状态、完成内容、已知的 watcher 集成测试原生崩溃仍未处理，以及下一步。

- [ ] **Step 8: 核对最终状态并报告**

Run:

```bash
git status --short --branch
git log -3 --oneline
```

Expected: 工作区干净，`main` 与 `origin/main` 对齐；最终报告提供代码行为、测试证据、提交、推送结果、CI/CD 状态和 Obsidian 更新位置。

