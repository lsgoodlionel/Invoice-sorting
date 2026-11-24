// 统计交叉表单元格 → 清单页筛选链接。
import type { DateBasis, ExpenseStatus, StatsColumn, StatsCrossBy, StatsGroupBy, StatsRow } from '../api/types';
import { expensesLink, type ExpenseFilters } from './expenseFilters';

const MONTH_KEY = /^(\d{4})-(\d{2})$/;
const NON_VOID_STATUSES: ExpenseStatus[] = ['spent', 'invoiced', 'complete', 'sent', 'reimbursed'];

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

type Dimension = StatsGroupBy | StatsCrossBy;

function dimensionFilter(groupBy: Dimension, key: string, label: string): Partial<ExpenseFilters> {
  switch (groupBy) {
    case 'category':
      return key === 'none' ? { uncategorized: true } : { categoryId: numericKey(key) };
    case 'project':
      return { projectId: numericKey(key) };
    case 'merchant':
      return { q: label };
    case 'month': {
      const bounds = monthBounds(key);
      return bounds ? { period: { preset: 'custom', ...bounds } } : {};
    }
    case 'travel_scope':
      return key === 'local' || key === 'nonlocal' ? { travelScope: key } : {};
    case 'batch':
      return key === 'none' ? { unbatched: true } : { batchId: numericKey(key) };
    case 'lab_platform':
      return key === 'required' ? { requiresLabPlatform: true } : key === 'not_required' ? { requiresLabPlatform: false } : key === 'none' ? { uncategorized: true } : {};
    case 'status':
      return { statuses: [key as ExpenseStatus] };
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
  crossBy?: StatsCrossBy;
  column?: StatsColumn | null;
}

export function statsCellLink({ start, end, dateBasis, groupBy, row, status, crossBy, column }: DrillInput): string {
  return expensesLink({
    period: { preset: 'custom', start, end },
    dateBasis,
    statuses: status ? [status] : NON_VOID_STATUSES,
    ...dimensionFilter(groupBy, row.key, row.label),
    ...(crossBy && column ? dimensionFilter(crossBy, column.key, column.label) : {}),
  });
}
