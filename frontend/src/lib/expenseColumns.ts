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

export function readExpenseColumns(): ExpenseColumnKey[] {
  try {
    const parsed = JSON.parse(localStorage.getItem('expense-columns-v1') ?? '[]');
    if (!Array.isArray(parsed)) return [...DEFAULT_EXPENSE_COLUMNS];
    const valid = parsed.filter((value): value is ExpenseColumnKey => EXPENSE_COLUMN_OPTIONS.some((item) => item.value === value));
    return valid.length ? valid : [...DEFAULT_EXPENSE_COLUMNS];
  } catch {
    return [...DEFAULT_EXPENSE_COLUMNS];
  }
}

export function saveExpenseColumns(columns: readonly ExpenseColumnKey[]): void {
  localStorage.setItem('expense-columns-v1', JSON.stringify(columns));
}
