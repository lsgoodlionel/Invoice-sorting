# API 契约（前后端共同遵守）

- 基础地址：`/api`，服务仅监听 `127.0.0.1:8765`。开发时前端 Vite 代理 `/api` → `http://127.0.0.1:8765`。
- 统一响应信封：`{ "ok": true, "data": <payload>, "error": null }`；失败 `{ "ok": false, "data": null, "error": "中文错误说明" }`，HTTP 状态码 400/404/409/422。
- 金额一律以 **分（整数）** 传输，字段名以 `_cents` 结尾；前端负责格式化为 `¥1,234.00`。
- 日期 `YYYY-MM-DD`；时间 ISO 8601 带时区。
- 枚举值见 `backend/src/invoice_sorting/common/constants.py`：
  - ExpenseStatus：`spent` 已支出 / `invoiced` 已开票 / `complete` 凭证齐全 / `sent` 已外发 / `reimbursed` 已报销 / `void` 不报销/作废
  - AttachmentKind：`invoice` 发票 / `order` 订单明细 / `payment` 支付记录 / `acceptance` 验收单 / `contract` 合同 / `application` 申购单 / `itinerary` 行程单 / `meal_form` 工作餐单 / `meeting` 会议材料 / `software_form` 软件服务报账单 / `statement` 情况说明 / `transport` 往来交通凭证 / `other` 其他
  - ChecklistLevel：`required` / `suggested`；ChecklistState：`missing` / `present` / `not_needed`
  - BatchStatus：`draft` 待外发 / `sent` 已外发 / `partial` 部分到账 / `received` 已到账
  - ExportLayout：`by_expense` / `by_kind`；DateBasis：`spent` / `invoiced` / `sent` / `received`

## 0 登录认证与用户管理

应用自身负责认证。系统内置管理员账户 `admin`：首次打开网页为 admin 设置初始密码；未设置前，除公开端点外的所有 `/api/*` 均不可访问。管理员可添加用户并设置密码。所有用户共用同一账本，操作记录上传人/操作人。

**首次启动按部署形态分两种**：单账套部署首次打开网页为内置 `admin` 设置初始密码；多账套部署首次打开网页（**裸域名**，没有账套子域名）创建**首个平台管理员**——用户名由使用者填写（默认 `admin`），同时开通「平台运营」账套（`platform`）并设为其管理员。两者都走 `POST /api/auth/setup`，安装命令里不需要任何账号信息。命令行 `grant-platform-admin` 继续可用（忘记密码、批量运维、没有浏览器时）。

账号、密码与会话统一存放在**控制库**（`control.db` 的 `account` / `membership` / `auth_session`）；账套（租户）业务库中的 `app_user` 是同一账号在该账套内的**镜像**（`app_user.id == account.id`，同步用户名/姓名/角色/启用状态，不再使用其 `password_hash`），上传人与操作人展示照旧。角色是**账套内**的：同一账号在不同账套可以有不同角色。

部署形态（`INVOICE_SORTING_DEPLOYMENT_MODE`）影响返回字段：**单账套部署（single，默认）下所有接口都不返回账套字段，界面完全不出现账套概念**；多账套部署（saas）才有下面标注“仅多账套”的字段与端点。

### 0.1 认证

| 方法 | 路径 | 请求 | 返回 data |
| --- | --- | --- | --- |
| GET | `/api/auth/status` | 公开 | `{ auth_enabled: boolean, password_set: boolean, authenticated: boolean, user: CurrentUser \| null }`（password_set 表示 admin 已设置密码；多账套裸域名下表示**控制库已初始化**——已有任意账号或已开通 `platform` 账套，全新部署为 false，提示创建首个平台管理员）；仅多账套时追加 `multi_tenant: true` 与 `tenant: TenantBrief \| null`（未登录为 null） |
| POST | `/api/auth/setup` | 公开；`{ password, username? }`。**单账套**：只用 `password`，仅在 admin 尚未设置密码时可用，否则 409“已设置过初始密码，请直接登录”。**多账套**（裸域名）：控制库为空时创建首个平台管理员，`username` 默认 `admin`（3–32 位字母数字下划线点连字符，否则 422），一旦已有任意账号或已开通 `platform` 账套即 409“已创建过平台管理员，请直接登录”；带账套子域名访问时照旧按该账套解析，账套不存在 404“账套不存在”。并发只会有一个请求成功（进程内串行 + 用户名与账套 slug 唯一约束） | `{ authenticated: true, user: CurrentUser }`，写入会话 Cookie；仅多账套时追加 `tenant`（首次为 `{ slug: "platform", name: "平台运营" }`），该账号被标记为平台管理员，可直接访问 `/api/platform/*` |
| POST | `/api/auth/login` | 公开；`{ username, password }`；用户名不存在、密码错误、账户已停用或在本账套内被停用统一 401“用户名或密码错误”；admin 未设置密码 409“请先设置初始密码”；失败过多 429“尝试次数过多，请 N 分钟后再试”；账号完全不是该账套成员 403“当前账号不属于该账套，请联系管理员开通”；账号未加入任何账套 403“当前账号尚未加入任何账套，请联系管理员开通” | `{ authenticated: true, user: CurrentUser }`，写入会话 Cookie；仅多账套时追加 `tenant` |
| POST | `/api/auth/logout` | 需登录 | `null` |
| POST | `/api/auth/password` | 需登录；`{ current_password, new_password }`；当前密码错误 400；关闭认证时 400“未启用登录认证，无法修改密码” | `null`；本人其他会话失效，当前会话保留 |
| POST | `/api/auth/join` | 公开；`{ code, username, password, display_name? }` 凭邀请码加入账套，见 0.4 | 同 login |
| GET | `/api/auth/tenants` | 需登录；**仅多账套**，单账套 404“当前为单账套部署，无需切换账套” | `TenantOption[]`（当前账号可进入的账套，按加入顺序） |
| POST | `/api/auth/switch-tenant` | 需登录；**仅多账套**；`{ slug }`（小写字母数字连字符，否则 422）；账套不存在 404；不是成员 403“当前账号不属于该账套，请联系管理员开通” | `{ authenticated: true, user: CurrentUser, tenant: TenantBrief }`，会话的当前账套被改写 |

```ts
type UserRole = "admin" | "member"
type CurrentUser = { id: number; username: string; display_name: string; role: UserRole }
type UserRef = { id: number; display_name: string } // 用于上传人/操作人展示
// 仅多账套部署返回
type TenantBrief = { slug: string; name: string }
type TenantOption = TenantBrief & { is_current: boolean }
```

- 用户名：3–32 个字符，字母、数字、下划线、点、连字符（不区分大小写唯一，存储为小写，首尾空白忽略）；`admin` 为内置管理员用户名。不符合 422“用户名需为 3–32 个字符，只能包含字母、数字、下划线、点、连字符”。login 的 username 不校验格式（去首尾空白、按小写匹配），仅超过 1024 字符 422。
- 姓名 display_name：1–32 个字符（去首尾空白后计算），默认同用户名；不符合 422。
- 密码规则：8–128 个字符（setup、new_password、创建用户、管理员重置密码）；不符合 422。login 的 password 与 current_password 不校验下限，仅超过 1024 字符 422。
- 会话 Cookie `invoice_session`：HttpOnly、SameSite=Lax、Path=/，30 天，按小时续期；HTTPS 时 Secure；服务端（控制库）只存令牌 SHA-256，会话关联账号与**当前所选账套**。
- 账套定位顺序：子域名（配置了 `tenant_host_suffix` 时）→ 会话记录的当前账套。子域名指定了账套时会校验该账号在其中有启用中的成员关系，否则 403“当前账号不属于该账套，请联系管理员开通”；多账套部署定位不到账套时 400“无法确定当前账套，请重新登录”，**绝不回退到默认账套**。账套不存在 404“账套不存在”。
- 未认证：401“请先登录”；admin 未设置密码时 401“请先设置初始密码”（此时其他用户也无法访问，status 的 authenticated=false、user=null）。已登录但账户被停用：该用户所有会话立即失效（401“请先登录”）。
- 权限不足：403“需要管理员权限”（先于请求体校验，普通用户提交非法请求体也返回 403）。
- 公开端点：`/api/health`、`/api/auth/status`、`/api/auth/setup`、`/api/auth/login`、`/api/auth/join`。
- 登录失败限制：按客户端 IP，15 分钟内失败 5 次锁定 15 分钟（同前）。
- `INVOICE_SORTING_AUTH_ENABLED=false`：关闭认证，status 返回 auth_enabled=false、authenticated=true、user=null；所有端点放行，管理员限定端点也放行；操作人记为空。
- 旧版单一密码自动迁移（启动时幂等执行）：若不存在 admin 用户则创建 admin（姓名“管理员”），有旧密码时沿用该密码，并删除旧密码设置；未关联用户的旧会话全部失效（需重新登录）。新库启动即有未设置密码的 admin。多账套部署的账套由控制面开通成员，业务库不预置 admin 镜像。
- 升级到控制面账号后：账号 id 与密码哈希不变、已有会话一并搬到控制库，**老用户无需重新登录、密码不变**。业务库 `app_user.password_hash` 列保留但不再使用（便于回退旧版本）。
- 忘记 admin 密码：服务器执行 `invoice-sorting reset-password`（清除 admin 密码与 admin 全部会话，网页回到“设置初始密码”；其他用户会话保留，但在 admin 重新设置密码前同样 401“请先设置初始密码”）；`invoice-sorting reset-password --user 用户名` 清除指定用户密码并删除其全部会话（has_password=false，该用户需管理员在网页中重新设置密码）。用户不存在时 stderr 输出“用户不存在：用户名”并以退出码 1 结束。

### 0.2 用户管理（仅管理员）

| 方法 | 路径 | 请求 | 返回 data |
| --- | --- | --- | --- |
| GET | `/api/users` | — | `User[]`（**本账套**的成员，按加入顺序） |
| POST | `/api/users` | `{ username, display_name?, password, role? }`（role 默认 `member`）；用户名已存在 409“用户名已存在”（用户名全局唯一，别的账套占用了也算） | `User`，同时加入本账套 |
| PATCH | `/api/users/{id}` | `{ display_name?, role?, is_active? }`；不是本账套成员 404“用户不存在” | `User`；`role`/`is_active` 改的是**本账套内**的身份，停用后其会话全部失效 |
| POST | `/api/users/{id}/password` | `{ password }` 管理员重置；不是本账套成员 404 | `null`；该用户所有会话失效（重置自己的密码时当前会话也失效，需重新登录） |

管理员只能管理**自己账套**的成员：别的账套的账号一律按“用户不存在”处理，平台级用户管理属于运营后台（后续批次）。

```ts
type User = {
  id: number; username: string; display_name: string; role: UserRole; is_active: boolean;
  has_password: boolean; created_at: string; last_login_at: string | null
}
```

- 约束（400，中文说明）：不能停用自己（“不能停用自己”）或把自己改为普通用户（“不能把自己改为普通用户”）；**每个账套**必须至少保留一名启用中且已设置密码的管理员（修改会让最后一名这样的管理员失去资格时 400“系统必须至少保留一名启用中且已设置密码的管理员”）；内置 `admin` 不能改用户名（本接口不提供改用户名）。关闭认证时无“自己”，仅检查管理员保留规则。
- 普通用户（member）可使用：收集、清单、批次、统计、附件、导入、经费项目新建/编辑、修改自己的密码。
- 仅管理员：用户管理；`PUT /api/settings`；分类的新建/修改/删除；凭证清单规则的新建/修改/删除；`POST /api/backup`。对应 GET 端点所有登录用户可读。

### 0.3 操作人记录

- `Attachment.uploaded_by: UserRef | null`（上传人；收件箱自动导入为 null，前端显示“收件箱”；关闭认证时为 null）
- `ExpenseSummary.created_by: UserRef | null`、`ExpenseDetail.created_by`
- `StatusEvent.actor: UserRef | null`（自动推进时为触发该变化的用户，收件箱为 null）
- `Batch.created_by: UserRef | null`、`ExportRecord.created_by: UserRef | null`
- 已停用用户的历史记录仍显示其姓名。

### 0.4 邀请码

租户管理员生成邀请码，受邀人凭邀请码 + 用户名 + 密码加入本账套。单账套部署接口同样可用，只是界面不暴露入口。

| 方法 | 路径 | 请求 | 返回 data |
| --- | --- | --- | --- |
| GET | `/api/invites` | 仅管理员 | `Invite[]`（本账套，新的在前） |
| POST | `/api/invites` | 仅管理员；`{ role?, expires_on? }`（role 默认 `member`，非法 422；expires_on 默认 7 天后） | `Invite` |
| POST | `/api/auth/join` | 公开；`{ code, username, password, display_name? }` | 同 `/api/auth/login`，并写入会话 Cookie |

```ts
type Invite = {
  id: number; code: string; role: UserRole; expires_on: string | null;
  is_used: boolean; used_at: string | null; created_at: string
}
```

- 邀请码一次性使用：已用 409“邀请码已被使用，请向管理员重新索取”；不存在 404“邀请码无效，请向管理员重新索取”；过期 410“邀请码已过期，请向管理员重新索取”；账套不可用 403“该账套当前不可加入，请联系管理员”。
- 用户名已存在时必须填写**该账号的登录密码**，否则 401“该用户名已存在，请填写它的登录密码”；已经是本账套成员 409“该账号已在此账套中，请直接登录”。用户名不存在则按该用户名开通新账号。
- 与登录共用失败限制（按客户端 IP），防止穷举邀请码。

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
// 打车/出行/交通/差旅/出差/住宿/酒店→差旅交通、线缆/数码/数据→易耗品、图书→图书、设备→设备，或同名分类），否则走分类建议。
// 住宿组（含酒店订单或住宿发票，差旅住宿凭证设计第 3 节）另行汇总：金额 = 组内全部发票价税合计之和（订单不计；
// 只有订单时取订单金额，invoice_exempt=false）；商家 = 酒店名（订单 details.hotel，否则住宿发票销售方）；
// 摘要 = “酒店名 N晚 + 交通 K 张”；分类 = 差旅交通；日期 = 入住日期（无订单时取住宿发票开票日期）。
// suggested_action：含“可能重复”提示 → skip；有强匹配 → attach；含发票或有金额和日期 → create；否则 skip。
// link_reasons 取值：订单号一致、文件名一致、金额与日期一致、境外订单与银行交易日期一致、卡号末四位一致、
// 酒店发票与订单一致（金额相同 + 酒店名与销售方有 ≥2 字公共子串 + 开票日期在入住至离店后 30 天内）、
// 往返酒店所在地的交通凭证（交通日期在入住−1 至离店+1 天内，且起点或终点包含酒店城市）。
// MatchCandidate.reasons 另有：“往返 苏州 的交通凭证（入住 08-15、离店 08-16）”（住宿记录 ↔ 新交通凭证，+60）、
// “酒店发票与订单一致”（住宿发票 ↔ 只有订单的记录，+70）。

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
- 一个 ConfirmGroup 最多含一张发票；住宿组（含住宿发票或酒店订单）可以是一张住宿发票 + 任意张交通票发票（details.vehicle 非空或税收分类为旅客运输等），两张住宿发票不可同组。否则 400“每组最多一张发票（住宿可附多张交通票发票）：“a.pdf”、“b.pdf””。
- 组内错误统一加前缀：单文件为 `文件“name”：`，多文件为 `文件“name”等 N 个：`。
- 整个请求原子：任一组失败则全部回滚（含文件移动）；成功后本次提交的附件（含 skip）移出会话，会话清空后再提交返回 404“导入会话已过期，请重新导入”。
- 记录时间线备注为“导入凭证”。
- attach：文件挂到目标记录，发票 `confirmed=true`、凭证 `confirmed=true`；目标记录缺商家/原币信息时补上，不覆盖日期。
- 金额并入（attach、收件箱自动确认、`bulk-assign`、`PATCH /api/attachments/{id}` 改归属、`POST /api/expenses/{id}/attachments` 补传共用）：记录此前已有发票且挂上后发票合计变化时——记录金额等于挂之前的发票合计则更新为新的发票合计，时间线追加一条 from_status = to_status 的事件，note 为“并入交通票 ¥120.00，金额更新为 ¥620.00”（记录内无交通票发票时写“发票”）；金额被手动改过则不改，note 为“并入交通票 ¥120.00，金额未自动调整（已手动修改过）”。记录此前没有发票（首张发票）时不改金额。
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

`ChecklistRule = { id, category_id: number|null, attachment_kind, level, condition: { amount_gte?: number, amount_lt?: number, is_online?: boolean, is_nonlocal?: boolean, detail_platform?: boolean, content_keywords?: string[], exclude_keywords?: string[] }, hint }`

条件全部满足才触发：`is_nonlocal` 为外地发票；`detail_platform` 为销售方属于已带明细平台；`invoice_exempt` 为免发票记录；`content_keywords` 为发票内容（税收分类、商品名称、销售方）或记录商家、摘要包含任一关键词（每个 1–20 字，最多 20 个），`exclude_keywords` 为包含任一关键词则不触发。默认规则（版本 5）：差旅交通的“订单明细”仅在含“住宿/酒店/宾馆/旅馆/民宿/客栈”时必需（酒店订单），“行程单”对这些住宿发票不触发。版本 6：同条件下“往来交通凭证”（`transport`）必需，提示“往返酒店所在地与本地的火车/飞机/汽车/轮船票或行程单”；该项在记录有 `transport` 类型附件，或有 details.vehicle 非空的发票（交通票发票）时视为已有。旧库启动时追加一次（幂等）。默认新增通用规则：`{ is_nonlocal: true, detail_platform: false }` → 订单明细（必需），提示“外地发票需附网购订单截图（京东、当当、圆迈等已带明细平台可免）；非网购外地购品需随差旅报销并说明”。

### 私有化授权（licensing 模块）

| 方法 | 路径 | 请求 | 返回 data |
| --- | --- | --- | --- |
| GET | `/api/license/status` | — | `LicenseStatus` |
| POST | `/api/license/recheck` | —（仅管理员，60 秒内只能触发一次，超频 429） | `LicenseStatus` |
| POST | `/api/platform/license/verify` | `{ license_key, instance_id, app_version?, users?, tenants? }`（控制面签发，无需登录） | `{ token: string }` |

`LicenseStatus = { state: "active"|"grace"|"readonly"|"unlicensed_ok"|"not_applicable", message: string, instance_id: string, valid_until: string|null, grace_until: string|null, max_users: number, last_checked_at: string|null, last_error: string, server_reachable: boolean }`

- `active` 正常；`grace` 已过期但在宽限期内（顶部提示条，仍可写）；`readonly` 只读；
  `unlicensed_ok` 未配置授权密钥（本机自用，不限制）；`not_applicable` 多租户模式不适用。
- `readonly` 期间所有写接口（POST/PUT/PATCH/DELETE 的 `/api/*`）返回 **403** 并附中文原因；
  GET、`/api/auth/*`（登录）、`/api/backup`（备份）与批次导出仍可用。
- `message` 可直接作为提示条文案；`server_reachable=false` 表示当前联系不上授权服务（不降级）。

### 套餐与额度（quota 模块）

| 方法 | 路径 | 请求 | 返回 data |
| --- | --- | --- | --- |
| GET | `/api/quota` | —（需登录） | `Quota` |

```ts
type QuotaLine = {
  key: "users" | "storage" | "expenses";
  label: string;            // 成员数量 / 存储空间 / 本月新增记录
  unit: string;             // 人 / MB / 条
  limit: number;            // 0 表示不限制
  used: number;             // 与 limit 同单位（存储向下取整到 MB）
  remaining: number | null; // 不限制时为 null
  is_unlimited: boolean;
  is_exceeded: boolean;     // used >= limit，即再做一次就会超
}

type Quota = {
  enforced: boolean;        // 单账套部署为 false，plan/usage 为 null、limits 为 []，界面不显示任何上限
  plan: { code, name, max_users, max_storage_mb, max_expenses_per_month, features } | null;
  usage: { users, storage_bytes, storage_mb, expenses_this_month, measured_at: string|null, is_stale: boolean } | null;
  limits: QuotaLine[];
  is_readonly: boolean;
  readonly_reason: "" | "tenant_suspended" | "tenant_closed" | "tenant_expired";
  readonly_message: string; // 可直接作为提示条文案
  status: "active" | "suspended" | "closed";
  expires_on: string | null;      // YYYY-MM-DD
  expires_in_days: number | null; // 负数表示已过期
}
```

- 额度**只在多账套部署生效**。账套未绑定套餐时按内置「免费版」（3 人 / 1024 MB / 每月 200 条）计算；
  控制库中同时有一行 `plan.code = "free"` 供运营后台选用。任一上限为 0 表示该项不限制。
- 账套 `status != active` 或 `expires_on` 已过（到期日当天仍可写）→ **只读**：GET、`/api/auth/*`、
  `/api/backup` 与批次导出照常，其余 `/api/*` 写请求返回 **403** 并附 `readonly_message`。
  停用/关闭/到期三种文案分别说明原因与处理办法。
- 额度只拦“会让用量变大”的动作，修改与删除始终放行（否则超限后无法清理自救）：
  - `POST /api/expenses`、`POST /api/attachments/create-expenses` → 当月新增记录
  - `POST /api/expenses/{id}/attachments`、`POST /api/imports*` → 存储（导入同时看两项）
  - `POST /api/users`、`POST /api/auth/join`（邀请码加入）→ 成员数量
- 超限同样返回 **403**，`error` 指明是哪一项、上限多少、当前多少以及可以怎么办，例如
  “本月新增记录已达套餐上限（团队版：每月 200 条，本月已新增 200 条），无法再新建记录。请升级套餐，或等下月额度重置。”
- `usage.storage_bytes` 为文件库目录累计字节，带缓存（默认 5 分钟）：过期时先返回旧值
  （`usage.is_stale = true`）再后台刷新，因此刚上传的文件可能晚几分钟才反映到数字上。
- 用量每日一行写入控制库 `usage_snapshot`（读取本接口时顺带更新当天行，同账套 5 分钟至多写一次）。
- 运营后台改套餐、改到期日、停用与恢复**立即生效**：每个写请求都会重新读取控制库中的租户行与套餐，
  不存在需要重启或等待缓存过期的情况（仅存储用量的数字有上述缓存）。

### 平台运营后台（platform_admin 模块）

前缀 `/api/platform`，**全部仅限平台管理员**（控制库 `account.is_platform_admin`）。
单账套私有化部署退化为「管理员即平台管理员」，前端不出现入口。
租户管理员即使访问自己账套的平台路径也返回 **403**（跨账套越权红线）。

多租户部署下平台后台常从**裸域名**访问：`/api/platform/*` 按登录会话所属账号的成员关系
定位账套，不依赖子域名，因此不会出现「无法确定当前账套」400；未登录为 401，
登录了但不是平台管理员为 403。

| 方法 | 路径 | 请求 | 返回 data |
| --- | --- | --- | --- |
| GET | `/api/platform/overview` | — | `{ tenants, active_tenants, accounts, storage_bytes, expenses_created }` |
| GET | `/api/platform/tenants` | `?q=&page=1&page_size=20`（q 匹配标识或名称） | `{ items: PlatformTenant[], total, page, page_size }` |
| POST | `/api/platform/tenants` | `{ slug, name?, plan_code?, expires_on?, admin_username?, admin_password?, admin_display_name?, with_invite? }` | `PlatformTenant & { admin: User\|null, invite: Invite\|null }` |
| GET | `/api/platform/tenants/{slug}` | — | `PlatformTenant` |
| PATCH | `/api/platform/tenants/{slug}` | `{ name?, plan_code?, expires_on?, status? }` | `PlatformTenant` |
| GET/POST | `/api/platform/tenants/{slug}/members` | POST `{ username, display_name?, password?, role }` | `User[]` / `User` |
| PATCH | `/api/platform/tenants/{slug}/members/{id}` | `{ display_name?, role?, is_active? }` | `User` |
| POST | `/api/platform/tenants/{slug}/members/{id}/password` | `{ password }` | `null` |
| GET/POST | `/api/platform/tenants/{slug}/invites` | POST `{ role?, expires_on? }` | `Invite[]` / `Invite` |
| POST | `/api/platform/tenants/{slug}/export` | `{ include_packages? }` → 异步任务 | `ExportJob` |
| GET | `/api/platform/tenants/{slug}/export/{job}/status` | — | `ExportJob` |
| GET | `/api/platform/tenants/{slug}/export/{job}` | — | ZIP 文件流 |
| GET/POST | `/api/platform/plans` | POST `{ code, name?, max_users?, max_storage_mb?, max_expenses_per_month?, features? }` | `Plan[]` / `Plan` |
| PATCH/DELETE | `/api/platform/plans/{id}` | PATCH 同上（不含 code）；被账套引用时 DELETE 409 | `Plan` / `null` |
| GET/POST | `/api/platform/licenses` | POST `{ customer_name, max_users?, valid_until?, note?, features? }` | `LicenseRecord[]` / `LicenseRecord` |
| PATCH | `/api/platform/licenses/{id}` | `{ customer_name?, max_users?, valid_until?, status?, note? }`（status=`revoked` 即吊销） | `LicenseRecord` |
| POST | `/api/platform/licenses/{id}/unbind` | — 清空绑定实例，供客户换机 | `LicenseRecord` |
| DELETE | `/api/platform/licenses/{id}` | — | `null` |

```ts
type PlatformTenant = {
  slug: string; name: string; status: "active"|"suspended"|"closed";
  plan: { code: string; name: string } | null;
  expires_on: string | null;      // 为空表示长期有效
  member_count: number;           // 启用中的成员数
  usage: { day, users, storage_bytes, expenses_created } | null;  // 最近一天的用量快照
  created_at: string;
}
type Plan = { id, code, name, max_users, max_storage_mb, max_expenses_per_month, features, created_at }  // 额度 0 = 不限
type LicenseRecord = {
  id: number; license_key: string; is_key_visible: boolean;   // 列表中只有前后各 4 位（ABCD****WXYZ）
  customer_name: string; max_users: number; valid_until: string | null;
  status: "active"|"revoked"; bound_instance_id: string; note: string;
  issued_at: string | null; checked_at: string | null; created_at: string;
}
type ExportJob = { job, slug, status: "running"|"done"|"failed", file, size, file_count, error, download_url }
```

- **授权密钥只在签发响应里返回一次原文**（`is_key_visible=true`），之后只能看到脱敏值，服务端日志也不记录密钥。
- PATCH 只处理请求里**出现过**的字段：传 `null` 表示清空（`plan_code: null` 取消套餐、`expires_on: null` 长期有效），不传表示不修改。
- 账套改为 `suspended` 或 `closed` 后立即释放该账套的数据库连接；成员只能登录查看与导出（额度模块负责只读降级）。
- 开通账套时必须给出 `admin_username` + `admin_password`，或 `with_invite=true` 签发一张管理员邀请码。
- 成员接口的目标账套由路径中的 slug 指定，与当前请求解析到的账套无关；业务规则（不能停用自己、账套至少保留一名启用且有密码的管理员）与账套内「设置 → 用户管理」一致。

**首个平台管理员（离线开通）**：`invoice-sorting grant-platform-admin --username x [--password ...] [--display-name ...]`。
命令只读写本机 `control.db`：建号（或复用同名账号）、标记 `is_platform_admin`，并确保该账号至少属于一个账套
（多租户部署自动开通 `platform`「平台运营」账套，单账套部署挂到 `default`），否则登录会被「尚未加入任何账套」拒绝。

### 诊断与故障上报（diagnostics 模块）

设计见 [运行日志与故障上报 · 设计](日志与故障上报_设计.md)。两个端点都**仅管理员**可用（非管理员 403），
且在只读降级期间仍然放行——服务出问题的时候恰恰最需要诊断包。

| 方法 | 路径 | 请求 | 返回 data |
| --- | --- | --- | --- |
| GET | `/api/diagnostics/status` | —（仅管理员） | `DiagnosticsStatus` |
| POST | `/api/diagnostics/collect` | `{ upload?: boolean, reason?: "manual"\|"crash"\|"error" }`（仅管理员） | `DiagnosticsReport` |

```ts
type DiagnosticsReport = {
  created_at: string; reason: "manual" | "crash" | "error";
  fingerprint: string;          // 故障指纹（异常类型 + 堆栈顶部位置），手工生成时为空
  package: string; size: number;   // 包文件名与字节数（包在 <数据目录>/日志/诊断包/）
  residue: string[];            // 残留自检结果，非空表示拒绝上传
  is_truncated: boolean;        // 日志过大已截断
  is_uploaded: boolean; repo_path: string; message: string;
}
type DiagnosticsStatus = {
  upload_enabled: boolean;      // 仓库与令牌都配置了才为 true
  repo: string;                 // 未启用上传时为空串
  app: string; instance: string; log_file: string;
  last: DiagnosticsReport | null;
  throttle: { daily_used: number; daily_remaining: number; tracked_fingerprints: number };
}
```

- **默认不上传**：未配置 `INVOICE_SORTING_LOG_REPO` 与 `INVOICE_SORTING_LOG_TOKEN` 时，
  `upload: true` 也只生成本机诊断包，`message` 说明原因。
- 日志仓库令牌只从环境变量读，**不落库、不写日志、不进诊断包，也不会出现在任何响应里**。
- 包内所有文本都已脱敏；打包后自检发现疑似残留（邮箱、手机号、证件号、卡号、密钥形态）即拒绝上传。
