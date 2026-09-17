// 统计交叉表单元格 → 清单页筛选链接。
import type { DateBasis, ExpenseStatus, StatsGroupBy, StatsRow } from '../api/types';
import { expensesLink, type ExpenseFilters } from './expenseFilters';

const MONTH_KEY = /^(\d{4})-(\d{2})$/;

function monthBounds(key: string): { start: string; end: string } | null {
  const match = MONTH_KEY.exec(key);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  if (month < 1 || month > 12) return null;
  const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return { start: `${key}-01`, end: `${key}-${String(lastDay).padStart(2, '0')}` };
}

function numericKey(key: string): number | null {
  return /^\d+$/.test(key) ? Number(key) : null;
}

function groupFilter(groupBy: StatsGroupBy, row: StatsRow): Partial<ExpenseFilters> {
  switch (groupBy) {
    case 'category':
      return { categoryId: numericKey(row.key) };
    case 'project':
      return { projectId: numericKey(row.key) };
    case 'merchant':
      return { q: row.label };
    case 'month': {
      const bounds = monthBounds(row.key);
      return bounds ? { period: { preset: 'custom', ...bounds } } : {};
    }
    default:
      return {};
  }
}

export interface DrillInput {
  start: string;
  end: string;
  dateBasis: DateBasis;
  groupBy: StatsGroupBy;
  row: StatsRow;
  status: ExpenseStatus | null;
}

export function statsCellLink({ start, end, dateBasis, groupBy, row, status }: DrillInput): string {
  return expensesLink({
    period: { preset: 'custom', start, end },
    dateBasis,
    statuses: status ? [status] : [],
    ...groupFilter(groupBy, row),
  });
}
