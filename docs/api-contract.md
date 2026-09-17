# API 契约（前后端共同遵守）

- 基础地址：`/api`，服务仅监听 `127.0.0.1:8765`。开发时前端 Vite 代理 `/api` → `http://127.0.0.1:8765`。
- 统一响应信封：`{ "ok": true, "data": <payload>, "error": null }`；失败 `{ "ok": false, "data": null, "error": "中文错误说明" }`，HTTP 状态码 400/404/409/422。
- 金额一律以 **分（整数）** 传输，字段名以 `_cents` 结尾；前端负责格式化为 `¥1,234.00`。
- 日期 `YYYY-MM-DD`；时间 ISO 8601 带时区。
- 枚举值见 `backend/src/invoice_sorting/common/constants.py`：
  - ExpenseStatus：`spent` 已支出 / `invoiced` 已开票 / `complete` 凭证齐全 / `sent` 已外发 / `reimbursed` 已报销 / `void` 不报销/作废
  - AttachmentKind：`invoice` 发票 / `order` 订单明细 / `payment` 支付记录 / `acceptance` 验收单 / `contract` 合同 / `application` 申购单 / `itinerary` 行程单 / `meal_form` 工作餐单 / `meeting` 会议材料 / `software_form` 软件服务报账单 / `statement` 情况说明 / `other` 其他
  - ChecklistLevel：`required` / `suggested`；ChecklistState：`missing` / `present` / `not_needed`
  - BatchStatus：`draft` 待外发 / `sent` 已外发 / `partial` 部分到账 / `received` 已到账
  - ExportLayout：`by_expense` / `by_kind`；DateBasis：`spent` / `invoiced` / `sent` / `received`

## 1 数据形状

```ts
type Category = { id: number; name: string; color: string; keywords: string[]; route_hint: string; sort: number; archived: boolean }
type Project  = { id: number; code: string; name: string; owner: string; active: boolean }

type InvoiceData = {
  invoice_no: string | null; issued_on: string | null; total_cents: number | null; tax_cents: number | null;
  seller_name: string; seller_tax_id: string; buyer_name: string; buyer_tax_id: string;
  item_summary: string; invoice_type: string; parser: string; confirmed: boolean;
  buyer_mismatch: boolean            // 与设置中的购方抬头不一致
}

type Attachment = {
  id: number; expense_id: number | null; kind: AttachmentKind; kind_label: string;
  original_name: string; file_name: string; mime: string; size: number; created_at: string;
  url: string;                       // GET 该地址返回文件内容（inline）
  invoice: InvoiceData | null
}

type ChecklistItem = {
  id: number; attachment_kind: AttachmentKind; kind_label: string;
  level: "required" | "suggested"; state: "missing" | "present" | "not_needed";
  reason: string; hint: string
}

type StatusEvent = { id: number; from_status: ExpenseStatus | null; to_status: ExpenseStatus; is_manual: boolean; note: string; at: string }

type ExpenseSummary = {               // 列表行
  id: number; spent_on: string; amount_cents: number; merchant: string; summary: string;
  category_id: number | null; category_name: string | null; category_color: string | null;
  project_id: number | null; project_name: string | null;
  status: ExpenseStatus; status_label: string; status_manual: boolean;
  missing_count: number;              // 必需且 missing 的清单项数
  batch_id: number | null; batch_name: string | null;
  attachment_count: number; invoice_no: string | null
}

type ExpenseDetail = ExpenseSummary & {
  pay_method: string; is_online: boolean; note: string; void_reason: string;
  sent_on: string | null; reimbursed_on: string | null; reimbursed_cents: number;
  folder_path: string; route_hint: string;
  attachments: Attachment[]; checklist: ChecklistItem[]; timeline: StatusEvent[];
  created_at: string; updated_at: string
}

type Batch = {
  id: number; name: string; project_id: number | null; project_name: string | null;
  status: BatchStatus; status_label: string;
  sent_on: string | null; sent_via: string; receiver: string; external_no: string;
  received_on: string | null; received_cents: number; note: string; created_at: string;
  item_count: number; total_cents: number; missing_item_count: number   // 含必需缺项的记录数
}
type BatchDetail = Batch & { expenses: ExpenseSummary[]; exports: ExportRecord[] }
type ExportRecord = { id: number; layout: ExportLayout; file_name: string; url: string; sha256: string; item_count: number; total_cents: number; created_at: string }
```

## 2 端点

### 支出记录（expenses 模块）

| 方法 | 路径 | 请求 | 返回 data |
| --- | --- | --- | --- |
| GET | `/api/expenses` | query: `start`,`end`(含),`date_basis`(默认 spent),`category_id`,`project_id`,`status`(可多个，逗号分隔),`q`(商家/摘要/发票号),`batch_id`,`unbatched`(bool),`page`(1),`page_size`(默认 50, 最大 500) | `{ items: ExpenseSummary[], total: number, total_cents: number, status_counts: { [status]: { count, amount_cents } } }` |
| POST | `/api/expenses` | `{ spent_on, amount_cents, merchant, summary?, category_id?, project_id?, pay_method?, is_online?, note? }` | `ExpenseDetail` |
| GET | `/api/expenses/{id}` | — | `ExpenseDetail` |
| PATCH | `/api/expenses/{id}` | 上述任意字段 | `ExpenseDetail`（自动重算清单、状态、文件夹名） |
| DELETE | `/api/expenses/{id}` | — | `null`（软删除，文件移到回收站） |
| POST | `/api/expenses/{id}/status` | `{ status, note? }`；`void` 必须带 note；`{ status: null }` 表示取消手动、恢复自动 | `ExpenseDetail` |
| POST | `/api/expenses/{id}/attachments` | multipart：`files`(多个)，`kind`(可选，不传则自动判断) | `ExpenseDetail` |

### 附件与清单

| 方法 | 路径 | 请求 | 返回 data |
| --- | --- | --- | --- |
| GET | `/api/attachments/unassigned` | — | `Attachment[]`（待归属） |
| GET | `/api/attachments/{id}/file` | — | 文件流（非信封） |
| GET | `/api/attachments/{id}/thumbnail` | — | PNG 缩略图（PDF 首页/图片缩放，非信封） |
| PATCH | `/api/attachments/{id}` | `{ kind?, expense_id? }`（expense_id=null 表示移回待归属） | `Attachment` |
| DELETE | `/api/attachments/{id}` | — | `null`（移入回收站） |
| PATCH | `/api/checklist-items/{id}` | `{ state: "not_needed" \| "missing", reason? }` | `ExpenseDetail` |

### 导入（importer 模块）

| 方法 | 路径 | 请求 | 返回 data |
| --- | --- | --- | --- |
| POST | `/api/imports` | multipart：`files` | `ImportSession` |
| POST | `/api/imports/{session_id}/confirm` | `{ rows: [{ row_id, action: "create" \| "attach" \| "skip", expense_id?, spent_on, amount_cents, merchant, summary, category_id, project_id? }] }` | `{ created: number[], attached: number[], skipped: number }`（expense id 列表） |

```ts
type ImportRow = {
  row_id: string; attachment: Attachment;             // 已入库（未归属）
  is_invoice: boolean;
  suggested: { spent_on: string | null; amount_cents: number | null; merchant: string; summary: string; category_id: number | null };
  match: { expense_id: number; merchant: string; amount_cents: number; spent_on: string } | null;  // 匹配到的“已支出”记录
  warnings: string[]                                   // 如“购方名称与设置不一致”“金额校验不一致”
}
type ImportSession = {
  session_id: string; rows: ImportRow[];               // 发票行
  attachments: Attachment[];                           // 非发票文件 → 待归属
  duplicates: { original_name: string; existing_expense_id: number | null; reason: string }[];
  errors: { original_name: string; error: string }[]
}
```

### 批次（batches 模块）

| 方法 | 路径 | 请求 | 返回 data |
| --- | --- | --- | --- |
| GET | `/api/batches` | query: `status?` | `Batch[]` |
| POST | `/api/batches` | `{ name, project_id?, note? }` | `BatchDetail` |
| GET | `/api/batches/{id}` | — | `BatchDetail` |
| PATCH | `/api/batches/{id}` | `{ name?, project_id?, note?, sent_via?, receiver?, external_no? }` | `BatchDetail` |
| DELETE | `/api/batches/{id}` | 仅 draft 可删；记录回到未分批 | `null` |
| POST | `/api/batches/{id}/items` | `{ add?: number[], remove?: number[], force?: boolean }`；加入含必需缺项的记录且 force=false 时返回 409 并在 error 中说明；项目不一致同样 409 | `BatchDetail` |
| POST | `/api/batches/{id}/export` | `{ layout: "by_expense" \| "by_kind" }` | `ExportRecord` |
| GET | `/api/exports/{id}/file` | — | ZIP 文件流 |
| POST | `/api/batches/{id}/sent` | `{ sent_on, sent_via?, receiver?, external_no? }` | `BatchDetail` |
| POST | `/api/batches/{id}/received` | `{ received_on, expense_ids?: number[] }`（不传=全部） | `BatchDetail` |

### 统计（stats 模块）

`GET /api/stats?start=&end=&date_basis=spent&group_by=category|project|merchant|month`

```ts
type Stats = {
  start: string; end: string; date_basis: DateBasis;
  totals: { spent_cents: number; pending_cents: number; in_transit_cents: number; reimbursed_cents: number; void_cents: number };
  // spent=非作废合计；pending=spent/invoiced/complete；in_transit=sent；reimbursed=已到账金额；void=作废
  rows: { key: string; label: string; by_status: { [status]: { count: number; amount_cents: number } }; total_cents: number }[];
  months: { month: string; amount_cents: number }[]     // 趋势（按所选口径日期的 YYYY-MM）
}
```

`GET /api/stats/export?...同上` → XLSX 文件流。
`GET /api/dashboard` → `{ missing: ExpenseSummary[] (有必需缺项，最多 20), overdue: Batch[] (已外发超过 overdue_days 未到账), spent_without_invoice: ExpenseSummary[] (已支出超过 14 天仍无发票), unassigned_count: number, month_totals: Stats["totals"] }`

### 设置（settings 模块）

| 方法 | 路径 | 请求 | 返回 data |
| --- | --- | --- | --- |
| GET | `/api/settings` | — | `{ buyer_name, buyer_tax_id, overdue_days, data_dir, inbox_dir }` |
| PUT | `/api/settings` | `{ buyer_name?, buyer_tax_id?, overdue_days? }` | 同上 |
| GET/POST | `/api/categories` | POST `{ name, color?, keywords?, route_hint? }` | `Category[]` / `Category` |
| PATCH/DELETE | `/api/categories/{id}` | DELETE 为归档 | `Category` / `null` |
| GET/POST | `/api/projects` | POST `{ code?, name, owner? }` | `Project[]` / `Project` |
| PATCH/DELETE | `/api/projects/{id}` | DELETE 为停用 | `Project` / `null` |
| GET/POST | `/api/checklist-rules` | POST `{ category_id|null, attachment_kind, level, condition, hint }` | `ChecklistRule[]` / `ChecklistRule` |
| PATCH/DELETE | `/api/checklist-rules/{id}` | | `ChecklistRule` / `null` |
| POST | `/api/backup` | — | `{ file: string }` |

`ChecklistRule = { id, category_id: number|null, attachment_kind, level, condition: { amount_gte?: number, amount_lt?: number, is_online?: boolean }, hint }`
