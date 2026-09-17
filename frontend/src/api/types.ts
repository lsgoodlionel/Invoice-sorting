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
  buyer_mismatch: boolean;
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

export type ExpensePatch = Partial<ExpenseCreate>;

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

export interface ImportSuggestion {
  spent_on: string | null;
  amount_cents: number | null;
  merchant: string;
  summary: string;
  category_id: number | null;
}

export interface ImportMatch {
  expense_id: number;
  merchant: string;
  amount_cents: number;
  spent_on: string;
}

export interface ImportRow {
  row_id: string;
  attachment: Attachment;
  is_invoice: boolean;
  suggested: ImportSuggestion;
  match: ImportMatch | null;
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
  rows: ImportRow[];
  attachments: Attachment[];
  duplicates: ImportDuplicate[];
  errors: ImportError[];
  notices: ImportNotice[];
}

export type ImportAction = 'create' | 'attach' | 'skip';

export interface ImportConfirmRow {
  row_id: string;
  action: ImportAction;
  expense_id?: number;
  spent_on: string;
  amount_cents: number;
  merchant: string;
  summary: string;
  category_id: number | null;
  project_id?: number | null;
}

export interface ImportConfirmResult {
  created: number[];
  attached: number[];
  skipped: number;
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
  data_dir: string;
  inbox_dir: string;
}

export type SettingsPatch = Partial<Pick<Settings, 'buyer_name' | 'buyer_tax_id' | 'overdue_days'>>;

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
