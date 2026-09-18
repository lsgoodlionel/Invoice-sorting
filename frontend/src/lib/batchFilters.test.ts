import { describe, expect, test } from 'vitest';
import { makeBatch } from '../test/fixtures';
import {
  DEFAULT_BATCH_FILTERS,
  batchDate,
  decodeBatchFilters,
  encodeBatchFilters,
  filterBatches,
  shanghaiDate,
  type BatchFilters,
} from './batchFilters';

const NOW = new Date('2026-09-18T04:00:00Z');

const batches = [
  makeBatch({ id: 1, status: 'draft', created_at: '2026-09-01T09:00:00+08:00' }),
  makeBatch({ id: 2, status: 'sent', created_at: '2026-08-31T17:30:00Z', sent_on: '2026-09-05' }),
  makeBatch({ id: 3, status: 'partial', created_at: '2026-07-10T10:00:00+08:00', sent_on: '2026-08-01', received_on: '2026-09-30' }),
  makeBatch({ id: 4, status: 'received', created_at: '2026-06-01T10:00:00+08:00', sent_on: '2026-06-02', received_on: '2026-10-01' }),
];

const run = (patch: Partial<BatchFilters>) =>
  filterBatches(batches, { ...DEFAULT_BATCH_FILTERS, ...patch }, NOW).map((batch) => batch.id);

describe('shanghaiDate', () => {
  test('converts ISO timestamps to the Asia/Shanghai calendar date', () => {
    expect(shanghaiDate('2026-08-31T17:30:00Z')).toBe('2026-09-01');
    expect(shanghaiDate('2026-08-31T15:59:59Z')).toBe('2026-08-31');
    expect(shanghaiDate('2026-09-01T00:10:00+08:00')).toBe('2026-09-01');
  });

  test('returns null for invalid input', () => {
    expect(shanghaiDate('not a date')).toBeNull();
    expect(shanghaiDate('')).toBeNull();
  });
});

describe('batchDate', () => {
  test('reads the field for each basis', () => {
    expect(batchDate(batches[1], 'created')).toBe('2026-09-01');
    expect(batchDate(batches[1], 'sent')).toBe('2026-09-05');
    expect(batchDate(batches[1], 'received')).toBeNull();
  });
});

describe('filterBatches', () => {
  test('defaults keep every batch', () => {
    expect(run({})).toEqual([1, 2, 3, 4]);
  });

  test('filters by status', () => {
    expect(run({ status: 'sent' })).toEqual([2]);
    expect(run({ status: 'received' })).toEqual([4]);
  });

  test('created basis uses Shanghai dates and inclusive bounds', () => {
    expect(run({ period: { preset: 'custom', start: '2026-09-01', end: '2026-09-01' } })).toEqual([1, 2]);
    expect(run({ period: { preset: 'this_month' } })).toEqual([1, 2]);
  });

  test('sent and received bases exclude batches without that date', () => {
    const range = { preset: 'custom' as const, start: '2026-08-01', end: '2026-09-30' };
    expect(run({ basis: 'sent', period: range })).toEqual([2, 3]);
    expect(run({ basis: 'received', period: range })).toEqual([3]);
  });

  test('open-ended custom ranges only check the given bound', () => {
    expect(run({ basis: 'received', period: { preset: 'custom', start: '2026-10-01' } })).toEqual([4]);
    expect(run({ period: { preset: 'custom', end: '2026-07-10' } })).toEqual([3, 4]);
  });

  test('all dates ignores the basis', () => {
    expect(run({ basis: 'received', period: { preset: 'all' } })).toEqual([1, 2, 3, 4]);
  });

  test('combines status and period', () => {
    expect(run({ status: 'draft', period: { preset: 'last_month' } })).toEqual([]);
  });
});

describe('URL encoding', () => {
  test('defaults decode from empty params and encode to nothing', () => {
    expect(decodeBatchFilters(new URLSearchParams())).toEqual(DEFAULT_BATCH_FILTERS);
    expect(encodeBatchFilters(new URLSearchParams('id=3'), DEFAULT_BATCH_FILTERS).toString()).toBe('id=3');
  });

  test('round-trips status, preset, custom range and basis while keeping other params', () => {
    const filters: BatchFilters = {
      status: 'partial',
      period: { preset: 'custom', start: '2026-01-01', end: '2026-03-31' },
      basis: 'received',
    };
    const params = encodeBatchFilters(new URLSearchParams('id=3'), filters);
    expect(params.get('id')).toBe('3');
    expect(params.get('batch_status')).toBe('partial');
    expect(params.get('batch_period')).toBe('custom');
    expect(params.get('batch_start')).toBe('2026-01-01');
    expect(params.get('batch_end')).toBe('2026-03-31');
    expect(params.get('batch_basis')).toBe('received');
    expect(decodeBatchFilters(params)).toEqual(filters);
  });

  test('preset drops stale custom bounds', () => {
    const params = encodeBatchFilters(
      new URLSearchParams('batch_start=2026-01-01&batch_end=2026-02-01'),
      { ...DEFAULT_BATCH_FILTERS, period: { preset: 'this_year' } },
    );
    expect(params.toString()).toBe('batch_period=this_year');
  });

  test('ignores invalid values', () => {
    const decoded = decodeBatchFilters(new URLSearchParams('batch_status=bogus&batch_basis=x&batch_period=nope'));
    expect(decoded).toEqual(DEFAULT_BATCH_FILTERS);
  });
});
