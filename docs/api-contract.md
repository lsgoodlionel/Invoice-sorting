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

## 0 登录认证

应用自身负责认证（不再使用 Nginx 登录弹窗）。首次打开网页设置初始密码；未设置初始密码前，除下列公开端点外的所有 `/api/*` 均不可访问。

| 方法 | 路径 | 请求 | 返回 data |
| --- | --- | --- | --- |
| GET | `/api/auth/status` | — 公开 | `{ auth_enabled: boolean, password_set: boolean, authenticated: boolean }` |
| POST | `/api/auth/setup` | 公开；`{ password }`，仅在尚未设置密码时可用，否则 409“已设置过初始密码，请直接登录” | `{ authenticated: true }`，并写入会话 Cookie |
| POST | `/api/auth/login` | 公开；`{ password }`；错误 401“密码错误”；未设置 409“请先设置初始密码”；失败过多 429“尝试次数过多，请 N 分钟后再试” | `{ authenticated: true }`，并写入会话 Cookie |
| POST | `/api/auth/logout` | 需登录 | `null`，清除 Cookie 并使该会话失效 |
| POST | `/api/auth/password` | 需登录；`{ current_password, new_password }`；当前密码错误 400 | `null`；其他设备会话全部失效，当前会话保留 |

- 密码规则：8–128 个字符（setup 的 `password`、修改密码的 `new_password`；不符合时 422，error 形如“参数错误：body.password 密码长度需为 8–128 个字符”）。login 的 `password` 与 `current_password` 不校验下限（长度不符按密码错误处理），仅超过 1024 字符时 422。
- 会话 Cookie：名称 `invoice_session`，HttpOnly、SameSite=Lax、Path=/，Max-Age 30 天；访问受保护端点或 status 时续期（距上次续期超过 1 小时才写库并重新下发 Cookie）；请求经 HTTPS（含来自本机反代的 `X-Forwarded-Proto: https`）时加 Secure。服务端只保存令牌的 SHA-256。
- 未认证访问受保护端点：401 `{ ok: false, error: "请先登录" }`；尚未设置密码时 error 为 `"请先设置初始密码"`。前端收到 401 时重新获取 `/api/auth/status` 并显示对应页面。
- 公开端点：`/api/health`、`/api/auth/status`、`/api/auth/setup`、`/api/auth/login`；前端静态文件始终可访问。
- 登录失败限制：同一客户端 IP（直连地址为 127.0.0.1/::1 时才信任代理头：优先 `X-Real-IP`，其次 `X-Forwarded-For` 的最后一个地址）15 分钟内失败 5 次锁定 15 分钟；锁定期间任何登录请求（含正确密码）返回 429，N 为向上取整的剩余分钟；登录成功清零。计数保存在进程内存，重启服务后清零。
- `INVOICE_SORTING_AUTH_ENABLED=false` 可关闭认证（仅限本机单人使用；status 返回 auth_enabled=false、authenticated=true）。
- 忘记密码：服务器执行 `invoice-sorting reset-password`，清空密码与全部会话，之后网页回到“设置初始密码”。

## 1 数据形状

```ts
type Category = { id: number; name: string; color: string; keywords: string[]; route_hint: string; sort: number; archived: boolean }
type Project  = { id: number; code: string; name: string; owner: string; active: boolean }

type InvoiceData = {
  invoice_no: string | null; issued_on: string | null; total_cents: number | null; tax_cents: number | null;
  seller_name: string; seller_tax_id: string; buyer_name: string; buyer_tax_id: string;
  item_summary: string; invoice_type: string; parser: string; confirmed: boolean;
  tax_category: string;               // 税收分类简称，如“纸制品”
  region_name: string;               // 开票地区，如“北京”，无法判断为 ""
  is_nonlocal: boolean;              // region_name 非空且不等于设置中的本地地区
  order_no: string;                  // 票面订单号，无则 ""
  detail_platform: boolean;          // 销售方属于已带明细的平台（设置 detail_platforms），外地订单截图可免
  buyer_mismatch: boolean            // 与设置中的购方抬头不一致
}

type Attachment = {
  id: number; expense_id: number | null; kind: AttachmentKind; kind_label: string;
  original_name: string; file_name: string; mime: string; size: number; created_at: string;
  url: string;                       // GET 该地址返回文件内容（inline）
  file_key: string;                  // 文件名键（设计 3.3），无则 ""
  invoice: InvoiceData | null;
  evidence: EvidenceData | null      // 非发票凭证识别结果，见“导入”一节
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
  attachment_count: number; invoice_no: string | null;
  region_name: string; is_nonlocal: boolean;   // 取该记录发票的开票地区；多张发票任一外地即为外地
  invoice_exempt: boolean;            // 免发票（境外消费等）
  currency: string; original_amount_cents: number | null    // 原币（CNY 时 original 为 null）
}

type ExpenseDetail = ExpenseSummary & {
  pay_method: string; is_online: boolean; note: string; void_reason: string;
  sent_on: string | null; reimbursed_on: string | null; reimbursed_cents: number;
  folder_path: string; route_hint: string;
  // invoice_exempt / currency / original_amount_cents 见 ExpenseSummary，均可 POST / PATCH
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
| GET | `/api/expenses` | query: `start`,`end`(含),`date_basis`(默认 spent),`category_id`,`project_id`,`status`(可多个，逗号分隔),`q`(商家/摘要/发票号),`batch_id`,`unbatched`(bool),`missing`(bool，仅含必需缺项),`page`(1),`page_size`(默认 50, 最大 500) | `{ items: ExpenseSummary[], total: number, total_cents: number, status_counts: { [status]: { count, amount_cents } } }` |
| POST | `/api/expenses` | `{ spent_on, amount_cents, merchant, summary?, category_id?, project_id?, pay_method?, is_online?, note?, invoice_exempt?(默认 false), currency?(3 位 ISO 大写，小写自动转大写，默认 "CNY"), original_amount_cents? }`；币种为 CNY 时 original_amount_cents 自动置空 | `ExpenseDetail` |
| GET | `/api/expenses/{id}` | — | `ExpenseDetail` |
| PATCH | `/api/expenses/{id}` | 上述任意字段 | `ExpenseDetail`（自动重算清单、状态、文件夹名） |
| DELETE | `/api/expenses/{id}` | — | `null`（软删除：移出草稿批次，文件移到回收站并删除附件记录；所在批次已外发时 409） |
| POST | `/api/expenses/{id}/status` | `{ status, note? }`；`void` 必须带 note，并自动移出草稿批次（批次已外发时 409）；`{ status: null }` 表示取消手动、恢复自动 | `ExpenseDetail` |
| POST | `/api/expenses/{id}/attachments` | multipart：`files`(多个)，`kind`(可选)。不传 kind 时自动识别：能解析为发票（且发票号未被占用）→ `invoice` 并写入 invoice（confirmed=true）；否则走凭证识别器，按 doc_type 设类型（order/receipt→order，payment→payment，itinerary→itinerary，未识别→文件名线索/关键词），写入 evidence（confirmed=true）。传 kind 时不识别 | `ExpenseDetail`（清单与状态已重算） |

### 附件与清单

| 方法 | 路径 | 请求 | 返回 data |
| --- | --- | --- | --- |
| GET | `/api/attachments/unassigned` | — | `Attachment[]`（待归属） |
| GET | `/api/attachments/{id}/file` | — | 文件流（非信封） |
| GET | `/api/attachments/{id}/thumbnail` | — | PNG 缩略图（PDF 首页/图片缩放，非信封） |
| PATCH | `/api/attachments/{id}` | `{ kind?, expense_id? }`（expense_id=null 表示移回待归属） | `Attachment` |
| DELETE | `/api/attachments/{id}` | — | `null`（移入回收站） |
| POST | `/api/attachments/bulk-delete` | `{ ids: number[] }`（仅限待归属附件，否则 409） | `{ deleted: number }` |
| POST | `/api/attachments/bulk-assign` | `{ ids: number[], expense_id: number \| null, kind?: AttachmentKind }` | `Attachment[]` |
| POST | `/api/attachments/create-expenses` | `{ ids: number[] }`：把所选待归属附件（发票与非发票凭证）先按导入规则分组，再逐组自动确认：强匹配 → 挂上；无匹配且有金额和日期 → 新建（无发票且境外/外币 → 免发票记录）；可能重复、缺金额或日期 → 跳过。已归属附件跳过（“已归属到记录 #id，无需生成”）；单组失败只跳过该组 | `{ created: number[], attached: number[], skipped: { id: number, original_name: string, reason: string }[] }`（skipped 按文件列出，reason 如“未识别到金额，请手工处理”“未识别到开票日期，请手工处理”“未识别到日期，请手工处理”“未识别到发票内容，请先重新识别或手工处理”或可能重复提示） |
| POST | `/api/attachments/reparse` | `{ ids: number[] }`：重新识别发票与非发票凭证（凭证走 OCR/识别器，更新 evidence；更新票面字段，保留 confirmed；同时重算 file_key。非发票凭证仅在待归属或类型为 other 时按识别结果改类型，已归属附件保留用户设置的类型；有发票数据的发票解析失败时保持原样；已归属记录的金额/日期/商家不自动改，商家为空时补上） | `Attachment[]` |
| PATCH | `/api/checklist-items/{id}` | `{ state: "not_needed" \| "missing", reason? }` | `ExpenseDetail` |

### 导入（importer 模块）— v2.1 按“凭证组”导入

设计说明见 `docs/凭证识别与自动归并_设计_v2.1.md`。

| 方法 | 路径 | 请求 | 返回 data |
| --- | --- | --- | --- |
| POST | `/api/imports` | multipart：`files` | `ImportSession` |
| POST | `/api/imports/start` | — 开始分文件导入（带进度的上传流程） | `{ session_id: string }` |
| POST | `/api/imports/{session_id}/files` | multipart：`file`（单个文件）；上传后立即入库并识别，响应即表示“处理完成” | `ImportFileResult` |
| POST | `/api/imports/{session_id}/finish` | — 对会话内全部已导入文件统一分组、匹配 | `ImportSession`（duplicates/errors/notices 为会话内累计） |
| POST | `/api/imports/{session_id}/confirm` | `{ groups: ConfirmGroup[] }` | `{ created: number[], attached: number[], skipped: number }`（expense id 列表；skipped 为留在待归属的文件数） |
| GET | `/api/attachments/{id}/candidates` | — 待归属附件的候选记录（同 5.2 匹配与评分）；强匹配（如有）排第一，其余最多 5 个按分数降序；附件已归属时 409，不存在 404 | `MatchCandidate[]` |

```ts
type EvidenceData = {                 // 非发票凭证识别结果（Attachment.evidence）
  doc_type: "order" | "receipt" | "payment" | "itinerary" | "unknown";
  recognizer: string;                 // jd_order / app_store_order / receipt / bank_transaction / wallet_bill / ride_itinerary / filename
  amount_cents: number | null; currency: string;          // 票面金额与币种（ISO，如 "USD"）
  cny_cents: number | null;           // 人民币金额（CNY 凭证等于 amount_cents；银行交易为入账人民币）
  occurred_on: string | null; merchant: string; item_name: string;
  order_no: string; card_last4: string; is_foreign: boolean; confirmed: boolean
}
// Attachment.evidence 为本类型；Attachment.file_key 为文件名键

type MatchCandidate = {
  expense_id: number; spent_on: string; merchant: string; amount_cents: number;
  currency: string; original_amount_cents: number | null;
  status: ExpenseStatus; missing_kinds: AttachmentKind[];
  score: number;                      // 订单号/文件名强匹配为 100；评分见设计 5.2，低于 45 分不列出
  reasons: string[]                   // 取值：订单号一致、文件名一致、金额相同、原币金额相同、日期相同、
                                      // 日期相差 N 天、商家相同、正好缺少{类型}、已有{类型}
}

type GroupSummary = {                 // 建议用于新建记录的字段
  spent_on: string | null; amount_cents: number | null;   // 人民币
  currency: string; original_amount_cents: number | null; // 原币（CNY 时 original 为 null）
  merchant: string; summary: string; category_id: number | null;
  is_online: boolean; invoice_exempt: boolean
}

type ImportGroup = {
  group_id: string;
  attachments: Attachment[];          // 已入库（未归属），含 invoice / evidence 识别结果
  link_reasons: string[];             // 组内关联依据，如 ["订单号一致"]、["文件名一致"]；单文件为 []
  summary: GroupSummary;
  match: MatchCandidate | null;       // 强匹配（建议挂上）
  candidates: MatchCandidate[];       // 其他候选（最多 5 个，按分数降序，不含 match）
  suggested_action: "create" | "attach" | "skip";
  warnings: string[]                  // 购方不一致、外地发票、可能重复（同订单同类型凭证已在 #id）等
}

// summary 来源：金额与日期取 发票 > 人民币支付记录 > 订单/收据；商家与摘要取 发票 > 订单/收据 > 支付记录；
// 原币取外币订单/收据（其次外币支付记录）；分类先按文件名首段分类词（办公→办公用品、软件→软件服务、
// 打车/出行→差旅交通、线缆/数码/数据→易耗品、图书→图书、设备→设备，或同名分类），否则走分类建议。
// suggested_action：含“可能重复”提示 → skip；有强匹配 → attach；含发票或有金额和日期 → create；否则 skip。
// link_reasons 取值：订单号一致、文件名一致、金额与日期一致、境外订单与银行交易日期一致、卡号末四位一致。

type ImportSession = {
  session_id: string;
  groups: ImportGroup[];
  duplicates: { original_name: string; existing_expense_id: number | null; reason: string }[];
  errors: { original_name: string; error: string }[];
  notices: { original_name: string; message: string }[]
}

type ImportFileResult = {
  original_name: string;
  status: "imported" | "duplicate" | "error";
  attachment: Attachment | null;      // imported 时为已入库附件（含 invoice / evidence 识别结果）
  recognized_as: string;              // 中文识别结论，如“发票”“发票（数电发票）”“订单明细（电商订单）”“支付记录（银行交易）”“未识别”
  message: string;                    // duplicate/error 的原因；imported 时可为提醒（如“无法识别发票内容，已作为附件导入”）或 ""
  existing_expense_id: number | null  // duplicate 时已存在的记录
}

type ConfirmGroup = {
  group_id: string;                   // 仅用于提示，可为前端生成的新组 id（如 "split-1"），不校验
  attachment_ids: number[];           // 用户可在组间移动文件：以此为准（须属于本次会话、仍待归属）
  kinds?: { [attachment_id: string]: AttachmentKind };    // 用户改过的附件类型
  action: "create" | "attach" | "skip";
  expense_id?: number;                // attach 必填
  // create 时使用（可被用户修改）：
  spent_on?: string; amount_cents?: number; currency?: string; original_amount_cents?: number | null;
  merchant?: string; summary?: string; category_id?: number | null; project_id?: number | null;
  is_online?: boolean; invoice_exempt?: boolean
}
```

- 分文件导入：`start` 返回空会话；`files` 每次一个文件，入库并提交后返回 `ImportFileResult`。文件保存/校验失败（类型不支持、为空、超过上限）与识别异常均返回 200 + `status="error"`（message 为中文原因），不是 4xx；会话不存在或已过期时 404“导入会话已过期，请重新导入”。
- `recognized_as`：发票为“发票”或“发票（票种）”；凭证为“附件类型（识别器）”，识别器名称：jd_order→电商订单、app_store_order→App Store 订单、receipt→收据/账单、bank_transaction→银行交易、wallet_bill→微信/支付宝账单、ride_itinerary→打车行程单、filename→按文件名判断（其他识别器只显示类型）；类型为“其他”、duplicate、error 时为“未识别”。
- duplicate：同一文件为“文件已导入”，同一发票号为“发票号码 xxx 已存在”；前端可并发上传，同一文件被并发上传多次时只有一个 imported，其余为 duplicate（“文件已导入”，existing_expense_id 为 null），不会返回 500。
- `finish` 可重复调用（如重试失败文件后再次 finish）：按会话内仍待归属的附件（已删除或已归属的跳过）从数据库重建分组，结果与一次性 `POST /api/imports` 相同；发票的支出日期沿用导入时的建议日期（差旅票优先乘车日期）。`confirm` 与一次性导入相同，确认后附件移出会话。
- attachment_ids 为准：每个附件须属于本次导入会话、仍待归属、且不重复出现在多个组，否则 400（如“文件“a.png”：不属于本次导入或已处理”“文件“a.png”：不能同时出现在多个组”“附件 #9 不存在或已处理”）。
- kinds 的键须是该组的附件 id，否则 400“类型设置中的附件 #id 不在该组”；先应用 kinds 再校验发票数。
- 一个 ConfirmGroup 最多含一张发票（否则 400“每组最多一张发票：“a.pdf”、“b.pdf””）。
- 组内错误统一加前缀：单文件为 `文件“name”：`，多文件为 `文件“name”等 N 个：`。
- 整个请求原子：任一组失败则全部回滚（含文件移动）；成功后本次提交的附件（含 skip）移出会话，会话清空后再提交返回 404“导入会话已过期，请重新导入”。
- 记录时间线备注为“导入凭证”。
- attach：文件挂到目标记录，发票 `confirmed=true`、凭证 `confirmed=true`；目标记录缺商家/原币信息时补上，不覆盖金额与日期。
- create：日期、金额、商家必填（“请填写支出日期”“请填写金额”“请填写商家”；invoice_exempt=true 时缺金额提示“请填写人民币金额”）。
- skip：只需 `{ group_id, attachment_ids, action: "skip" }`，文件留在待归属，计入 skipped。
- 收件箱与“生成记录”使用同一分组与匹配逻辑自动确认（设计 5.3）；收件箱同一轮检测到的文件一起导入以便互相归组；每组确认前重新匹配，单组失败只回滚该组。

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
| DELETE | `/api/exports/{id}` | — 删除资料包文件与导出记录（记录与凭证不受影响） | `null` |
| POST | `/api/batches/{id}/sent` | `{ sent_on, sent_via?, receiver?, external_no? }` | `BatchDetail` |
| POST | `/api/batches/{id}/received` | `{ received_on, expense_ids?: number[] }`（不传=全部）；草稿或已全部到账时 409 | `BatchDetail` |
| POST | `/api/batches/{id}/reopen` | — 回到草稿，清空外发/到账信息并重算记录状态；草稿批次 409 | `BatchDetail` |

### 统计（stats 模块）

`GET /api/stats?start=&end=&date_basis=spent&group_by=category|project|merchant|month`

```ts
type Stats = {
  start: string; end: string; date_basis: DateBasis;
  data_start: string | null;  // 所选区间与口径下最早有数据的日期（未删除、口径日期非空）；无数据为 null
  totals: { spent_cents: number; pending_cents: number; in_transit_cents: number; reimbursed_cents: number; void_cents: number };
  // spent=非作废合计；pending=spent/invoiced/complete；in_transit=sent；reimbursed=已到账金额；void=作废
  rows: { key: string; label: string; by_status: { [status]: { count: number; amount_cents: number } }; total_cents: number }[];
  months: { month: string; amount_cents: number }[]     // 趋势（按所选口径日期的 YYYY-MM），自 max(start, data_start 所在月初) 起逐月补 0 至 end；无数据时自 start 起
}
```

- rows.key：category/project 为 id 字符串，merchant 为商家名，month 为 `YYYY-MM`，空值为 `none`。区间超过 240 个月返回 400。
- data_start 仅影响 `months` 的起点，totals/rows 与导出（`/api/stats/export`）不受影响。

`GET /api/stats/export?...同上` → XLSX 文件流。
`GET /api/dashboard` → `{ missing: ExpenseSummary[] (有必需缺项，最多 20), overdue: Batch[] (已外发超过 overdue_days 未到账), spent_without_invoice: ExpenseSummary[] (已支出超过 14 天仍无发票), unassigned_count: number, month_totals: Stats["totals"] }`

### 设置（settings 模块）

| 方法 | 路径 | 请求 | 返回 data |
| --- | --- | --- | --- |
| GET | `/api/settings` | — | `{ buyer_name, buyer_tax_id, overdue_days, local_region, detail_platforms: string[], data_dir, inbox_dir }`（local_region 默认“上海”，detail_platforms 默认 ["京东","当当","圆迈"]） |
| PUT | `/api/settings` | `{ buyer_name?, buyer_tax_id?, overdue_days?, local_region?, detail_platforms? }` | 同上 |
| GET/POST | `/api/categories` | POST `{ name, color?, keywords?, route_hint? }` | `Category[]` / `Category` |
| PATCH/DELETE | `/api/categories/{id}` | DELETE 为归档 | `Category` / `null` |
| GET/POST | `/api/projects` | POST `{ code?, name, owner? }` | `Project[]` / `Project` |
| PATCH/DELETE | `/api/projects/{id}` | PATCH `{ code?, name?, owner?, active? }`；DELETE 为停用 | `Project` / `null` |
| GET/POST | `/api/checklist-rules` | POST `{ category_id|null, attachment_kind, level, condition, hint }` | `ChecklistRule[]` / `ChecklistRule` |
| PATCH/DELETE | `/api/checklist-rules/{id}` | | `ChecklistRule` / `null` |
| POST | `/api/backup` | — | `{ file: string }` |

`ChecklistRule = { id, category_id: number|null, attachment_kind, level, condition: { amount_gte?: number, amount_lt?: number, is_online?: boolean, is_nonlocal?: boolean, detail_platform?: boolean }, hint }`

条件全部满足才触发：`is_nonlocal` 为外地发票；`detail_platform` 为销售方属于已带明细平台；`invoice_exempt` 为免发票记录。默认新增通用规则：`{ is_nonlocal: true, detail_platform: false }` → 订单明细（必需），提示“外地发票需附网购订单截图（京东、当当、圆迈等已带明细平台可免）；非网购外地购品需随差旅报销并说明”。
