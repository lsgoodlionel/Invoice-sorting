// 严格对照 docs/api-contract.md。金额一律为“分”（整数）。

export type ExpenseStatus = 'spent' | 'invoiced' | 'complete' | 'sent' | 'reimbursed' | 'void';

export type AttachmentKind =
  | 'invoice'
  | 'order'
  | 'payment'
  | 'acceptance'
  | 'contract'
  | 'application'
  | 'itinerary'
  | 'transport'
  | 'meal_form'
  | 'meeting'
  | 'software_form'
  | 'statement'
  | 'other';

export type ChecklistLevel = 'required' | 'suggested';
export type ChecklistState = 'missing' | 'present' | 'not_needed';
export type BatchStatus = 'draft' | 'sent' | 'partial' | 'received';
export type ExportLayout = 'by_expense' | 'by_kind';
export type DateBasis = 'spent' | 'invoiced' | 'sent' | 'received';
export type StatsGroupBy = 'category' | 'project' | 'merchant' | 'month';

// —— 用户与操作人 ——
export type UserRole = 'admin' | 'member';

export interface CurrentUser {
  id: number;
  username: string;
  display_name: string;
  role: UserRole;
}

/** 上传人/操作人展示；null 表示收件箱自动处理、系统或关闭认证 */
export interface UserRef {
  id: number;
  display_name: string;
}

export interface User {
  id: number;
  username: string;
  display_name: string;
  role: UserRole;
  is_active: boolean;
  has_password: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface UserCreate {
  username: string;
  display_name?: string;
  password: string;
  role: UserRole;
}

export interface UserPatch {
  display_name?: string;
  role?: UserRole;
  is_active?: boolean;
}

export interface ApiEnvelope<T> {
  ok: boolean;
  data: T | null;
  error: string | null;
}

export interface Category {
  id: number;
  name: string;
  color: string;
  keywords: string[];
  route_hint: string;
  sort: number;
  archived: boolean;
}

export interface Project {
  id: number;
  code: string;
  name: string;
  owner: string;
  active: boolean;
}

export interface InvoiceData {
  invoice_no: string | null;
  issued_on: string | null;
  total_cents: number | null;
  tax_cents: number | null;
  seller_name: string;
  seller_tax_id: string;
  buyer_name: string;
  buyer_tax_id: string;
  item_summary: string;
  invoice_type: string;
  parser: string;
  confirmed: boolean;
  tax_category: string;
  region_name: string;
  is_nonlocal: boolean;
  order_no: string;
  detail_platform: boolean;
  buyer_mismatch: boolean;
  /** 发票解析出的结构化信息（交通票：date/from/to/vehicle/number/passenger）；旧数据可能为 null */
  details?: Record<string, string> | null;
}

export type EvidenceDocType = 'order' | 'receipt' | 'payment' | 'itinerary' | 'unknown';

/** 非发票凭证识别结果（订单、收据、银行交易、行程单等）。 */
export interface EvidenceData {
  doc_type: EvidenceDocType;
  recognizer: string;
  /** 票面金额（分，按 currency） */
  amount_cents: number | null;
  currency: string;
  /** 人民币金额（分） */
  cny_cents: number | null;
  occurred_on: string | null;
  merchant: string;
  item_name: string;
  order_no: string;
  card_last4: string;
  is_foreign: boolean;
  confirmed: boolean;
  /** 凭证结构化信息：酒店订单 city/hotel/check_in/check_out/nights/rooms/guest/platform；交通 date/from/to/vehicle/number/passenger */
  details?: Record<string, string> | null;
}

export interface Attachment {
  id: number;
  expense_id: number | null;
  kind: AttachmentKind;
  kind_label: string;
  original_name: string;
  file_name: string;
  mime: string;
  size: number;
  created_at: string;
  url: string;
  invoice: InvoiceData | null;
  evidence: EvidenceData | null;
  /** 文件名键（用于同组判断） */
  file_key: string;
  /** 上传人；收件箱自动导入为 null */
  uploaded_by: UserRef | null;
}

export interface ChecklistItem {
  id: number;
  attachment_kind: AttachmentKind;
  kind_label: string;
  level: ChecklistLevel;
  state: ChecklistState;
  reason: string;
  hint: string;
}

export interface StatusEvent {
  id: number;
  from_status: ExpenseStatus | null;
  to_status: ExpenseStatus;
  is_manual: boolean;
  note: string;
  at: string;
  /** 操作人；自动推进时为触发变化的用户，收件箱为 null */
  actor: UserRef | null;
}

export interface ExpenseSummary {
  id: number;
  spent_on: string;
  amount_cents: number;
  merchant: string;
  summary: string;
  category_id: number | null;
  category_name: string | null;
  category_color: string | null;
  project_id: number | null;
  project_name: string | null;
  status: ExpenseStatus;
  status_label: string;
  status_manual: boolean;
  missing_count: number;
  batch_id: number | null;
  batch_name: string | null;
  attachment_count: number;
  invoice_no: string | null;
  region_name: string;
  is_nonlocal: boolean;
  /** 免发票（境外消费等） */
  invoice_exempt: boolean;
  /** 原币种（ISO），人民币为 CNY */
  currency: string;
  /** 原币金额（分）；CNY 时为 null */
  original_amount_cents: number | null;
  created_by: UserRef | null;
}

export interface ExpenseDetail extends ExpenseSummary {
  pay_method: string;
  is_online: boolean;
  note: string;
  void_reason: string;
  sent_on: string | null;
  reimbursed_on: string | null;
  reimbursed_cents: number;
  folder_path: string;
  route_hint: string;
  attachments: Attachment[];
  checklist: ChecklistItem[];
  timeline: StatusEvent[];
  created_at: string;
  updated_at: string;
}

export interface StatusCount {
  count: number;
  amount_cents: number;
}

export type StatusCounts = Partial<Record<ExpenseStatus, StatusCount>>;

export interface ExpenseListResult {
  items: ExpenseSummary[];
  total: number;
  total_cents: number;
  status_counts: StatusCounts;
}

export interface ExpenseQuery {
  start?: string;
  end?: string;
  date_basis?: DateBasis;
  category_id?: number;
  project_id?: number;
  status?: ExpenseStatus[];
  q?: string;
  batch_id?: number;
  unbatched?: boolean;
  missing?: boolean;
  page?: number;
  page_size?: number;
}

export interface ExpenseCreate {
  spent_on: string;
  amount_cents: number;
  merchant: string;
  summary?: string;
  category_id?: number | null;
  project_id?: number | null;
  pay_method?: string;
  is_online?: boolean;
  note?: string;
}

export interface ExpensePatch extends Partial<ExpenseCreate> {
  invoice_exempt?: boolean;
  currency?: string;
  original_amount_cents?: number | null;
}

export interface Batch {
  id: number;
  name: string;
  project_id: number | null;
  project_name: string | null;
  status: BatchStatus;
  status_label: string;
  sent_on: string | null;
  sent_via: string;
  receiver: string;
  external_no: string;
  received_on: string | null;
  received_cents: number;
  note: string;
  created_at: string;
  item_count: number;
  total_cents: number;
  missing_item_count: number;
  created_by: UserRef | null;
}

export interface ExportRecord {
  id: number;
  layout: ExportLayout;
  file_name: string;
  url: string;
  sha256: string;
  item_count: number;
  total_cents: number;
  created_at: string;
  created_by: UserRef | null;
}

export interface BatchDetail extends Batch {
  expenses: ExpenseSummary[];
  exports: ExportRecord[];
}

export interface BatchCreate {
  name: string;
  project_id?: number | null;
  note?: string;
}

export interface BatchPatch {
  name?: string;
  project_id?: number | null;
  note?: string;
  sent_via?: string;
  receiver?: string;
  external_no?: string;
}

export interface BatchItemsChange {
  add?: number[];
  remove?: number[];
  force?: boolean;
}

export interface BatchSent {
  sent_on: string;
  sent_via?: string;
  receiver?: string;
  external_no?: string;
}

export interface BatchReceived {
  received_on: string;
  expense_ids?: number[];
}

export type ImportAction = 'create' | 'attach' | 'skip';

/** 与已有记录的匹配候选（分数与依据）。 */
export interface MatchCandidate {
  expense_id: number;
  spent_on: string;
  merchant: string;
  amount_cents: number;
  currency: string;
  original_amount_cents: number | null;
  status: ExpenseStatus;
  missing_kinds: AttachmentKind[];
  score: number;
  reasons: string[];
}

/** 建议用于新建记录的字段。 */
export interface GroupSummary {
  spent_on: string | null;
  /** 人民币金额（分） */
  amount_cents: number | null;
  currency: string;
  original_amount_cents: number | null;
  merchant: string;
  summary: string;
  category_id: number | null;
  is_online: boolean;
  invoice_exempt: boolean;
}

/** 一组同一笔支出的凭证。 */
export interface ImportGroup {
  group_id: string;
  attachments: Attachment[];
  link_reasons: string[];
  summary: GroupSummary;
  match: MatchCandidate | null;
  candidates: MatchCandidate[];
  suggested_action: ImportAction;
  warnings: string[];
}

export interface ImportDuplicate {
  original_name: string;
  existing_expense_id: number | null;
  reason: string;
}

export interface ImportError {
  original_name: string;
  error: string;
}

export interface ImportNotice {
  original_name: string;
  message: string;
}

export interface ImportSession {
  session_id: string;
  groups: ImportGroup[];
  duplicates: ImportDuplicate[];
  errors: ImportError[];
  notices: ImportNotice[];
}

export type ImportFileStatus = 'imported' | 'duplicate' | 'error';

/** 分文件导入：单个文件上传并处理完成后的结果。 */
export interface ImportFileResult {
  original_name: string;
  status: ImportFileStatus;
  /** imported 时为已入库附件 */
  attachment: Attachment | null;
  /** 中文识别结论，如“发票”“订单明细（京东订单）” */
  recognized_as: string;
  /** duplicate/error 的原因；imported 时可为提醒或空串 */
  message: string;
  existing_expense_id: number | null;
}

export interface ImportStartResult {
  session_id: string;
}

export interface ConfirmGroup {
  group_id: string;
  /** 以前端当前分组为准 */
  attachment_ids: number[];
  /** 用户改过的附件类型，键为附件 id */
  kinds?: Record<string, AttachmentKind>;
  action: ImportAction;
  expense_id?: number;
  spent_on?: string;
  amount_cents?: number;
  currency?: string;
  original_amount_cents?: number | null;
  merchant?: string;
  summary?: string;
  category_id?: number | null;
  project_id?: number | null;
  is_online?: boolean;
  invoice_exempt?: boolean;
}

export interface ImportConfirmInput {
  groups: ConfirmGroup[];
}

export interface ImportConfirmResult {
  created: number[];
  attached: number[];
  skipped: number;
}

export interface AttachmentBulkAssign {
  ids: number[];
  expense_id: number | null;
  kind?: AttachmentKind;
}

export interface CreateExpensesSkip {
  id: number;
  original_name: string;
  reason: string;
}

export interface CreateExpensesResult {
  created: number[];
  attached: number[];
  skipped: CreateExpensesSkip[];
}

export interface StatsTotals {
  spent_cents: number;
  pending_cents: number;
  in_transit_cents: number;
  reimbursed_cents: number;
  void_cents: number;
}

export interface StatsRow {
  key: string;
  label: string;
  by_status: StatusCounts;
  total_cents: number;
}

export interface Stats {
  start: string;
  end: string;
  date_basis: DateBasis;
  /** 所选区间与口径下最早有数据的日期；无数据为 null */
  data_start: string | null;
  totals: StatsTotals;
  rows: StatsRow[];
  months: { month: string; amount_cents: number }[];
}

export interface StatsQuery {
  start: string;
  end: string;
  date_basis: DateBasis;
  group_by: StatsGroupBy;
}

export interface Dashboard {
  missing: ExpenseSummary[];
  overdue: Batch[];
  spent_without_invoice: ExpenseSummary[];
  unassigned_count: number;
  month_totals: StatsTotals;
}

export interface Settings {
  buyer_name: string;
  buyer_tax_id: string;
  overdue_days: number;
  local_region: string;
  detail_platforms: string[];
  data_dir: string;
  inbox_dir: string;
}

export type SettingsPatch = Partial<Pick<Settings, 'buyer_name' | 'buyer_tax_id' | 'overdue_days' | 'local_region' | 'detail_platforms'>>;

export interface CategoryInput {
  name: string;
  color?: string;
  keywords?: string[];
  route_hint?: string;
}

export interface ProjectInput {
  code?: string;
  name: string;
  owner?: string;
}

export interface ChecklistCondition {
  amount_gte?: number;
  amount_lt?: number;
  is_online?: boolean;
  is_nonlocal?: boolean;
  detail_platform?: boolean;
  invoice_exempt?: boolean;
  /** 发票内容（税收分类、商品名称、销售方）或商家、摘要包含任一关键词才触发 */
  content_keywords?: string[];
  /** 包含任一关键词则不触发 */
  exclude_keywords?: string[];
}

export interface ChecklistRule {
  id: number;
  category_id: number | null;
  attachment_kind: AttachmentKind;
  level: ChecklistLevel;
  condition: ChecklistCondition;
  hint: string;
}

export type ChecklistRuleInput = Omit<ChecklistRule, 'id'>;

// —— 登录认证 ——
export interface AuthStatus {
  auth_enabled: boolean;
  password_set: boolean;
  authenticated: boolean;
  user: CurrentUser | null;
}

export interface AuthResult {
  authenticated: true;
  user: CurrentUser;
}

export interface LoginInput {
  username: string;
  password: string;
}

export interface ChangePasswordInput {
  current_password: string;
  new_password: string;
}
