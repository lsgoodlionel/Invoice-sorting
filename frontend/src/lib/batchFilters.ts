// 批次列表的前端筛选（批次数据量小）：状态 + 周期（创建/外发/到账日期口径）。
import type { Batch, BatchStatus } from '../api/types';
import { decodePeriod, encodePeriod, isValidDate, resolvePeriod, todayInShanghai, type Period } from './period';

export type BatchDateBasis = 'created' | 'sent' | 'received';
export type BatchStatusFilter = 'all' | BatchStatus;

export interface BatchFilters {
  status: BatchStatusFilter;
  period: Period;
  basis: BatchDateBasis;
}

export const DEFAULT_BATCH_FILTERS: BatchFilters = {
  status: 'all',
  period: { preset: 'all' },
  basis: 'created',
};

export const BATCH_STATUS_FILTER_OPTIONS: readonly { value: BatchStatusFilter; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'draft', label: '待外发' },
  { value: 'sent', label: '已外发' },
  { value: 'partial', label: '部分到账' },
  { value: 'received', label: '已到账' },
];

export const BATCH_DATE_BASIS_OPTIONS: readonly { value: BatchDateBasis; label: string }[] = [
  { value: 'created', label: '创建日期' },
  { value: 'sent', label: '外发日期' },
  { value: 'received', label: '到账日期' },
];

/** URL 查询参数名（批次页与 id 共存，加前缀避免与清单页参数混淆） */
const PARAM = { status: 'batch_status', period: 'batch_period', start: 'batch_start', end: 'batch_end', basis: 'batch_basis' } as const;

export function isBatchStatusFilter(value: string | null): value is BatchStatusFilter {
  return BATCH_STATUS_FILTER_OPTIONS.some((option) => option.value === value);
}

export function isBatchDateBasis(value: string | null): value is BatchDateBasis {
  return BATCH_DATE_BASIS_OPTIONS.some((option) => option.value === value);
}

/** ISO 时间 → Asia/Shanghai 日历日期 YYYY-MM-DD；无法解析返回 null。 */
export function shanghaiDate(iso: string): string | null {
  const time = Date.parse(iso);
  return Number.isNaN(time) ? null : todayInShanghai(new Date(time));
}

/** 批次在某口径下的日期；未外发/未到账为 null。 */
export function batchDate(batch: Batch, basis: BatchDateBasis): string | null {
  if (basis === 'created') return shanghaiDate(batch.created_at);
  const value = basis === 'sent' ? batch.sent_on : batch.received_on;
  return isValidDate(value) ? value : null;
}

/** 按状态与周期过滤（含边界）；有日期范围时，口径日期为空的批次被排除。 */
export function filterBatches<T extends Batch>(batches: readonly T[], filters: BatchFilters, now: Date = new Date()): T[] {
  const { start, end } = resolvePeriod(filters.period, now);
  const hasRange = start !== undefined || end !== undefined;
  return batches.filter((batch) => {
    if (filters.status !== 'all' && batch.status !== filters.status) return false;
    if (!hasRange) return true;
    const date = batchDate(batch, filters.basis);
    return date !== null && (start === undefined || date >= start) && (end === undefined || date <= end);
  });
}

export function decodeBatchFilters(params: URLSearchParams): BatchFilters {
  const periodParams = new URLSearchParams();
  [['period', PARAM.period], ['start', PARAM.start], ['end', PARAM.end]].forEach(([key, name]) => {
    const value = params.get(name);
    if (value !== null) periodParams.set(key, value);
  });
  const status = params.get(PARAM.status);
  const basis = params.get(PARAM.basis);
  return {
    status: isBatchStatusFilter(status) ? status : DEFAULT_BATCH_FILTERS.status,
    period: decodePeriod(periodParams, 'all'),
    basis: isBatchDateBasis(basis) ? basis : DEFAULT_BATCH_FILTERS.basis,
  };
}

/** 写入批次筛选，默认值不写；返回新的 URLSearchParams，保留其他参数（如 id）。 */
export function encodeBatchFilters(params: URLSearchParams, filters: BatchFilters): URLSearchParams {
  const next = new URLSearchParams(params);
  Object.values(PARAM).forEach((name) => next.delete(name));
  if (filters.status !== DEFAULT_BATCH_FILTERS.status) next.set(PARAM.status, filters.status);
  if (filters.basis !== DEFAULT_BATCH_FILTERS.basis) next.set(PARAM.basis, filters.basis);
  if (filters.period.preset === 'all') return next;
  const period = encodePeriod(new URLSearchParams(), filters.period);
  next.set(PARAM.period, period.get('period') ?? filters.period.preset);
  const start = period.get('start');
  const end = period.get('end');
  if (start) next.set(PARAM.start, start);
  if (end) next.set(PARAM.end, end);
  return next;
}
