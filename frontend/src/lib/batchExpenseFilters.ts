import type { ExpenseStatus, ExpenseSummary } from '../api/types';
import { ALL_STATUSES, STATUS_META } from './status';

/** 分类筛选中“未分类”的取值（category_id 为空）。 */
export const UNCATEGORIZED = 'none';
const UNCATEGORIZED_LABEL = '未分类';

export interface BatchExpenseFilter {
  /** 分类 id 字符串或 UNCATEGORIZED；null 表示全部 */
  category: string | null;
  /** 为空表示全部状态 */
  statuses: readonly ExpenseStatus[];
}

export interface Option<V extends string = string> {
  value: V;
  label: string;
}

export const EMPTY_BATCH_EXPENSE_FILTER: BatchExpenseFilter = { category: null, statuses: [] };

const categoryKey = (expense: ExpenseSummary): string =>
  expense.category_id === null ? UNCATEGORIZED : String(expense.category_id);

/** 批次详情记录表的本地过滤（不影响打包内容）。 */
export function filterBatchExpenses(
  expenses: readonly ExpenseSummary[],
  filter: BatchExpenseFilter,
): ExpenseSummary[] {
  return expenses.filter(
    (expense) =>
      (filter.category === null || categoryKey(expense) === filter.category) &&
      (filter.statuses.length === 0 || filter.statuses.includes(expense.status)),
  );
}

/** 批次内出现过的分类（去重，未分类排最后）。 */
export function batchCategoryOptions(expenses: readonly ExpenseSummary[]): Option[] {
  const named = new Map<string, string>();
  expenses.forEach((expense) => {
    if (expense.category_id !== null) named.set(String(expense.category_id), expense.category_name ?? UNCATEGORIZED_LABEL);
  });
  const options = [...named].map(([value, label]) => ({ value, label }));
  const hasUncategorized = expenses.some((expense) => expense.category_id === null);
  return hasUncategorized ? [...options, { value: UNCATEGORIZED, label: UNCATEGORIZED_LABEL }] : options;
}

/** 批次内出现过的状态，按工作流顺序。 */
export function batchStatusOptions(expenses: readonly ExpenseSummary[]): Option<ExpenseStatus>[] {
  const present = new Set(expenses.map((expense) => expense.status));
  return ALL_STATUSES.filter((status) => present.has(status)).map((status) => ({
    value: status,
    label: STATUS_META[status].label,
  }));
}
