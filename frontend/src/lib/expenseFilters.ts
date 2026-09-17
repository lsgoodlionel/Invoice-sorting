// 清单页筛选条件 ↔ URL 查询参数 ↔ 接口查询。
import type { DateBasis, ExpenseQuery, ExpenseStatus } from '../api/types';
import { decodePeriod, encodePeriod, resolvePeriod, type Period } from './period';
import { isDateBasis, parseStatusList } from './status';

export interface ExpenseFilters {
  period: Period;
  dateBasis: DateBasis;
  categoryId: number | null;
  projectId: number | null;
  statuses: ExpenseStatus[];
  q: string;
  batchId: number | null;
  unbatched: boolean;
  missingOnly: boolean;
}

export const DEFAULT_PAGE_SIZE = 200;

function parseId(raw: string | null): number | null {
  if (!raw || !/^\d+$/.test(raw)) return null;
  const value = Number(raw);
  return value > 0 ? value : null;
}

export function decodeExpenseFilters(params: URLSearchParams): ExpenseFilters {
  const basis = params.get('date_basis');
  return {
    period: decodePeriod(params),
    dateBasis: isDateBasis(basis) ? basis : 'spent',
    categoryId: parseId(params.get('category_id')),
    projectId: parseId(params.get('project_id')),
    statuses: parseStatusList(params.get('status')),
    q: params.get('q') ?? '',
    batchId: parseId(params.get('batch_id')),
    unbatched: params.get('unbatched') === 'true',
    missingOnly: params.get('missing') === 'true',
  };
}

function setOrDelete(params: URLSearchParams, key: string, value: string | null): void {
  if (value === null || value === '') params.delete(key);
  else params.set(key, value);
}

export function encodeExpenseFilters(filters: ExpenseFilters): URLSearchParams {
  const params = encodePeriod(new URLSearchParams(), filters.period);
  setOrDelete(params, 'date_basis', filters.dateBasis === 'spent' ? null : filters.dateBasis);
  setOrDelete(params, 'category_id', filters.categoryId === null ? null : String(filters.categoryId));
  setOrDelete(params, 'project_id', filters.projectId === null ? null : String(filters.projectId));
  setOrDelete(params, 'status', filters.statuses.length ? filters.statuses.join(',') : null);
  setOrDelete(params, 'q', filters.q.trim() || null);
  setOrDelete(params, 'batch_id', filters.batchId === null ? null : String(filters.batchId));
  setOrDelete(params, 'unbatched', filters.unbatched ? 'true' : null);
  setOrDelete(params, 'missing', filters.missingOnly ? 'true' : null);
  return params;
}

export function filtersToQuery(filters: ExpenseFilters, now: Date = new Date()): ExpenseQuery {
  const range = resolvePeriod(filters.period, now);
  return {
    ...range,
    date_basis: filters.dateBasis,
    ...(filters.categoryId !== null ? { category_id: filters.categoryId } : {}),
    ...(filters.projectId !== null ? { project_id: filters.projectId } : {}),
    ...(filters.statuses.length ? { status: filters.statuses } : {}),
    ...(filters.q.trim() ? { q: filters.q.trim() } : {}),
    ...(filters.batchId !== null ? { batch_id: filters.batchId } : {}),
    ...(filters.unbatched ? { unbatched: true } : {}),
    ...(filters.missingOnly ? { missing: true } : {}),
    page: 1,
    page_size: DEFAULT_PAGE_SIZE,
  };
}

/** 构造跳转清单页的链接。 */
export function expensesLink(partial: Partial<ExpenseFilters>): string {
  const base: ExpenseFilters = {
    period: { preset: 'all' },
    dateBasis: 'spent',
    categoryId: null,
    projectId: null,
    statuses: [],
    q: '',
    batchId: null,
    unbatched: false,
    missingOnly: false,
  };
  return `/expenses?${encodeExpenseFilters({ ...base, ...partial }).toString()}`;
}
