export type ExpenseColumnKey =
  | 'spent_on'
  | 'issued_on'
  | 'created_on'
  | 'summary'
  | 'item_name'
  | 'category'
  | 'lab_platform'
  | 'unit_price'
  | 'quantity'
  | 'amount'
  | 'invoice_no'
  | 'status'
  | 'evidence'
  | 'batch';

export const EXPENSE_COLUMN_OPTIONS: readonly { value: ExpenseColumnKey; label: string }[] = [
  { value: 'spent_on', label: '业务发生日期' },
  { value: 'issued_on', label: '发票开票日期' },
  { value: 'created_on', label: '凭证填报日期' },
  { value: 'summary', label: '商家 / 摘要' },
  { value: 'item_name', label: '名称' },
  { value: 'category', label: '分类' },
  { value: 'lab_platform', label: '平台申请' },
  { value: 'unit_price', label: '单价' },
  { value: 'quantity', label: '数量' },
  { value: 'amount', label: '总价' },
  { value: 'invoice_no', label: '发票号' },
  { value: 'status', label: '状态' },
  { value: 'evidence', label: '凭证' },
  { value: 'batch', label: '批次' },
];

export const DEFAULT_EXPENSE_COLUMNS: readonly ExpenseColumnKey[] = EXPENSE_COLUMN_OPTIONS.map((item) => item.value);

export const DEFAULT_EXPENSE_COLUMN_WIDTHS: Readonly<Record<ExpenseColumnKey, number>> = {
  spent_on: 120,
  issued_on: 120,
  created_on: 120,
  summary: 280,
  item_name: 220,
  category: 130,
  lab_platform: 120,
  unit_price: 110,
  quantity: 80,
  amount: 120,
  invoice_no: 180,
  status: 110,
  evidence: 90,
  batch: 160,
};

export interface ExpenseTablePreferences {
  order: ExpenseColumnKey[];
  visible: ExpenseColumnKey[];
  widths: Record<ExpenseColumnKey, number>;
}

export const DEFAULT_EXPENSE_TABLE_PREFERENCES: ExpenseTablePreferences = {
  order: [...DEFAULT_EXPENSE_COLUMNS],
  visible: [...DEFAULT_EXPENSE_COLUMNS],
  widths: { ...DEFAULT_EXPENSE_COLUMN_WIDTHS },
};

const isColumn = (value: unknown): value is ExpenseColumnKey =>
  typeof value === 'string' && EXPENSE_COLUMN_OPTIONS.some((item) => item.value === value);

const uniqueColumns = (values: unknown): ExpenseColumnKey[] => {
  if (!Array.isArray(values)) return [];
  return [...new Set(values.filter(isColumn))];
};

export function expenseTableStorageKey(userId: number | null): string {
  return `expense-table-v2:${userId ?? 'local'}`;
}

export function readExpenseTablePreferences(userId: number | null): ExpenseTablePreferences {
  try {
    const raw = localStorage.getItem(expenseTableStorageKey(userId));
    if (!raw) {
      const legacy = uniqueColumns(JSON.parse(localStorage.getItem('expense-columns-v1') ?? '[]'));
      return { ...DEFAULT_EXPENSE_TABLE_PREFERENCES, visible: legacy.length ? legacy : [...DEFAULT_EXPENSE_COLUMNS], widths: { ...DEFAULT_EXPENSE_COLUMN_WIDTHS } };
    }
    const parsed = JSON.parse(raw) as Partial<ExpenseTablePreferences>;
    const savedOrder = uniqueColumns(parsed.order);
    const order = [...savedOrder, ...DEFAULT_EXPENSE_COLUMNS.filter((key) => !savedOrder.includes(key))];
    const savedVisible = uniqueColumns(parsed.visible);
    const visible = savedVisible.length ? savedVisible : [...DEFAULT_EXPENSE_COLUMNS];
    const widths = { ...DEFAULT_EXPENSE_COLUMN_WIDTHS };
    for (const key of DEFAULT_EXPENSE_COLUMNS) {
      const width = parsed.widths?.[key];
      if (typeof width === 'number' && Number.isFinite(width)) widths[key] = Math.min(600, Math.max(64, Math.round(width)));
    }
    return { order, visible, widths };
  } catch {
    return { ...DEFAULT_EXPENSE_TABLE_PREFERENCES, order: [...DEFAULT_EXPENSE_COLUMNS], visible: [...DEFAULT_EXPENSE_COLUMNS], widths: { ...DEFAULT_EXPENSE_COLUMN_WIDTHS } };
  }
}

export function saveExpenseTablePreferences(userId: number | null, preferences: ExpenseTablePreferences): void {
  localStorage.setItem(expenseTableStorageKey(userId), JSON.stringify(preferences));
}
