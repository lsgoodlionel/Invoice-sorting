// 清单页筛选条件 ↔ URL 查询参数 ↔ 接口查询。
import type { DateBasis, ExpenseQuery, ExpenseSortBy, ExpenseStatus, SortOrder, TravelScope } from '../api/types';
import { decodePeriod, encodePeriod, resolvePeriod, type Period } from './period';
import { DEFAULT_VISIBLE_STATUSES, isDateBasis, parseStatusList } from './status';

export interface ExpenseFilters {
  period: Period;
  dateBasis: DateBasis;
  categoryId: number | null;
  uncategorized: boolean;
  projectId: number | null;
  statuses: ExpenseStatus[];
  q: string;
  batchId: number | null;
  unbatched: boolean;
  missingOnly: boolean;
  travelScope: TravelScope;
  requiresLabPlatform: boolean | null;
  sortBy: ExpenseSortBy;
  sortOrder: SortOrder;
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
    uncategorized: params.get('uncategorized') === 'true',
    projectId: parseId(params.get('project_id')),
    statuses: params.has('status') ? parseStatusList(params.get('status')) : [...DEFAULT_VISIBLE_STATUSES],
    q: params.get('q') ?? '',
    batchId: parseId(params.get('batch_id')),
    unbatched: params.get('unbatched') === 'true',
    missingOnly: params.get('missing') === 'true',
    travelScope: params.get('travel_scope') === 'local' || params.get('travel_scope') === 'nonlocal'
      ? params.get('travel_scope') as TravelScope
      : '',
    requiresLabPlatform: params.get('lab_platform') === 'required'
      ? true
      : params.get('lab_platform') === 'not_required' ? false : null,
    sortBy: ['date', 'summary', 'category', 'amount', 'status'].includes(params.get('sort_by') ?? '')
      ? params.get('sort_by') as ExpenseSortBy
      : 'date',
    sortOrder: params.get('sort_order') === 'asc' ? 'asc' : 'desc',
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
  setOrDelete(params, 'uncategorized', filters.uncategorized ? 'true' : null);
  setOrDelete(params, 'project_id', filters.projectId === null ? null : String(filters.projectId));
  const isDefaultStatus = filters.statuses.length === DEFAULT_VISIBLE_STATUSES.length
    && DEFAULT_VISIBLE_STATUSES.every((status) => filters.statuses.includes(status));
  setOrDelete(params, 'status', isDefaultStatus ? null : filters.statuses.join(','));
  setOrDelete(params, 'q', filters.q.trim() || null);
  setOrDelete(params, 'batch_id', filters.batchId === null ? null : String(filters.batchId));
  setOrDelete(params, 'unbatched', filters.unbatched ? 'true' : null);
  setOrDelete(params, 'missing', filters.missingOnly ? 'true' : null);
  setOrDelete(params, 'travel_scope', filters.travelScope || null);
  setOrDelete(params, 'lab_platform', filters.requiresLabPlatform === null ? null : filters.requiresLabPlatform ? 'required' : 'not_required');
  setOrDelete(params, 'sort_by', filters.sortBy === 'date' ? null : filters.sortBy);
  setOrDelete(params, 'sort_order', filters.sortOrder === 'desc' ? null : filters.sortOrder);
  return params;
}

export function filtersToQuery(filters: ExpenseFilters, now: Date = new Date()): ExpenseQuery {
  const range = resolvePeriod(filters.period, now);
  return {
    ...range,
    date_basis: filters.dateBasis,
    ...(filters.categoryId !== null ? { category_id: filters.categoryId } : {}),
    ...(filters.uncategorized ? { uncategorized: true } : {}),
    ...(filters.projectId !== null ? { project_id: filters.projectId } : {}),
    ...(filters.statuses.length ? { status: filters.statuses } : {}),
    ...(filters.q.trim() ? { q: filters.q.trim() } : {}),
    ...(filters.batchId !== null ? { batch_id: filters.batchId } : {}),
    ...(filters.unbatched ? { unbatched: true } : {}),
    ...(filters.missingOnly ? { missing: true } : {}),
    ...(filters.travelScope ? { travel_scope: filters.travelScope } : {}),
    ...(filters.requiresLabPlatform !== null ? { requires_lab_platform: filters.requiresLabPlatform } : {}),
    sort_by: filters.sortBy,
    sort_order: filters.sortOrder,
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
    uncategorized: false,
    projectId: null,
    statuses: [...DEFAULT_VISIBLE_STATUSES],
    q: '',
    batchId: null,
    unbatched: false,
    missingOnly: false,
    travelScope: '',
    requiresLabPlatform: null,
    sortBy: 'date',
    sortOrder: 'desc',
  };
  return `/expenses?${encodeExpenseFilters({ ...base, ...partial }).toString()}`;
}

const OPEN_PARAM = 'open';

/** 跳转清单页并打开指定记录详情。 */
export function expenseDetailLink(expenseId: number): string {
  return `${expensesLink({})}&${OPEN_PARAM}=${expenseId}`;
}

export function parseOpenExpenseId(params: URLSearchParams): number | null {
  return parseId(params.get(OPEN_PARAM));
}
