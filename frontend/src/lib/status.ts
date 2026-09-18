import type { AttachmentKind, BatchStatus, DateBasis, ExpenseStatus } from '../api/types';

export const STATUS_ORDER: readonly ExpenseStatus[] = ['spent', 'invoiced', 'complete', 'sent', 'reimbursed'];
export const ALL_STATUSES: readonly ExpenseStatus[] = [...STATUS_ORDER, 'void'];

export interface StatusMeta {
  label: string;
  shortLabel: string;
  /** Mantine 主题色名或 CSS 变量 */
  color: string;
  variant: 'light' | 'filled' | 'outline';
}

export const STATUS_META: Readonly<Record<ExpenseStatus, StatusMeta>> = {
  spent: { label: '已支出', shortLabel: '已支出', color: 'gray', variant: 'light' },
  invoiced: { label: '已开票', shortLabel: '已开票', color: 'blue', variant: 'light' },
  complete: { label: '凭证齐全', shortLabel: '凭证齐全', color: 'green', variant: 'light' },
  sent: { label: '已外发', shortLabel: '已外发', color: 'orange', variant: 'light' },
  reimbursed: { label: '已报销', shortLabel: '已报销', color: 'ink', variant: 'filled' },
  void: { label: '不报销/作废', shortLabel: '作废', color: 'gray', variant: 'outline' },
};

export function statusLabel(status: ExpenseStatus): string {
  return STATUS_META[status].label;
}

const EXEMPT_INVOICED_LABEL = '已收凭证';

/** 步进条标签：免发票记录第二步显示“已收凭证”。 */
export function stepLabel(status: ExpenseStatus, invoiceExempt: boolean): string {
  return invoiceExempt && status === 'invoiced' ? EXEMPT_INVOICED_LABEL : STATUS_META[status].label;
}

/** 主状态线上的序号（0 开始），作废为 -1。 */
export function statusRank(status: ExpenseStatus): number {
  return STATUS_ORDER.indexOf(status);
}

export function isStatus(value: string): value is ExpenseStatus {
  return (ALL_STATUSES as readonly string[]).includes(value);
}

/** 解析逗号分隔的状态列表，忽略非法值并去重。 */
export function parseStatusList(raw: string | null | undefined): ExpenseStatus[] {
  if (!raw) return [];
  const valid = raw.split(',').map((part) => part.trim()).filter(isStatus);
  return [...new Set(valid)];
}

/** 切换状态筛选，返回新数组。 */
export function toggleStatus(selected: readonly ExpenseStatus[], status: ExpenseStatus): ExpenseStatus[] {
  return selected.includes(status) ? selected.filter((item) => item !== status) : [...selected, status];
}

export const BATCH_STATUS_META: Readonly<Record<BatchStatus, { label: string; color: string }>> = {
  draft: { label: '待外发', color: 'gray' },
  sent: { label: '已外发', color: 'orange' },
  partial: { label: '部分到账', color: 'yellow' },
  received: { label: '已到账', color: 'ink' },
};

export const DATE_BASIS_OPTIONS: readonly { value: DateBasis; label: string }[] = [
  { value: 'spent', label: '支出日期' },
  { value: 'invoiced', label: '开票日期' },
  { value: 'sent', label: '外发日期' },
  { value: 'received', label: '到账日期' },
];

export function isDateBasis(value: string | null): value is DateBasis {
  return DATE_BASIS_OPTIONS.some((option) => option.value === value);
}

export const ATTACHMENT_KIND_LABELS: Readonly<Record<AttachmentKind, string>> = {
  invoice: '发票',
  order: '订单明细',
  payment: '支付记录',
  acceptance: '验收单',
  contract: '合同',
  application: '申购单',
  itinerary: '行程单',
  transport: '往来交通凭证',
  meal_form: '工作餐单',
  meeting: '会议材料',
  software_form: '软件服务报账单',
  statement: '情况说明',
  other: '其他',
};

export const ATTACHMENT_KIND_OPTIONS = (Object.keys(ATTACHMENT_KIND_LABELS) as AttachmentKind[]).map((kind) => ({
  value: kind,
  label: ATTACHMENT_KIND_LABELS[kind],
}));
