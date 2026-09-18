import { describe, expect, test } from 'vitest';
import { makeExpense } from '../test/fixtures';
import {
  DEFAULT_CANDIDATE_FILTERS,
  buildCandidateQuery,
  filterBatchCandidates,
  hasActiveFilters,
  selectableExpenses,
  type CandidateFilters,
} from './batchCandidates';

const NOW = new Date('2026-09-18T04:00:00Z');

const items = [
  makeExpense({ id: 1, merchant: '京东某店', summary: '鼠标', project_id: 7, missing_count: 1 }),
  makeExpense({ id: 2, merchant: '腾讯云', summary: '服务器', project_id: 8, invoice_no: '2644000001' }),
  makeExpense({ id: 3, merchant: '作废店', project_id: 7, status: 'void' }),
  makeExpense({ id: 4, merchant: '顺丰', summary: '快递', project_id: null }),
];

const withFilters = (patch: Partial<CandidateFilters>): CandidateFilters => ({ ...DEFAULT_CANDIDATE_FILTERS, ...patch });

describe('selectableExpenses', () => {
  test('excludes void expenses', () => {
    expect(selectableExpenses(items).map((e) => e.id)).toEqual([1, 2, 4]);
  });
});

describe('filterBatchCandidates', () => {
  const run = (patch: Partial<CandidateFilters>) => filterBatchCandidates(items, withFilters(patch)).map((e) => e.id);

  test('always drops void records', () => {
    expect(run({})).toEqual([1, 2, 4]);
  });

  test('searches merchant, summary and invoice number case-insensitively', () => {
    expect(run({ search: '快递' })).toEqual([4]);
    expect(run({ search: ' 腾讯 ' })).toEqual([2]);
    expect(run({ search: '26440' })).toEqual([2]);
    expect(run({ search: 'none' })).toEqual([]);
  });

  test('complete evidence keeps only records without missing items', () => {
    expect(run({ evidence: 'complete' })).toEqual([2, 4]);
    expect(run({ evidence: 'missing' })).toEqual([1, 2, 4]); // 缺凭证由服务端过滤
  });
});

describe('buildCandidateQuery', () => {
  test('defaults: only the batch project limit', () => {
    expect(buildCandidateQuery(DEFAULT_CANDIDATE_FILTERS, 7, NOW)).toEqual({ project_id: 7 });
    expect(buildCandidateQuery(DEFAULT_CANDIDATE_FILTERS, null, NOW)).toEqual({});
  });

  test('show all projects drops the batch project; an explicit project wins', () => {
    expect(buildCandidateQuery(withFilters({ showAllProjects: true }), 7, NOW)).toEqual({});
    expect(buildCandidateQuery(withFilters({ projectId: 9 }), 7, NOW)).toEqual({ project_id: 9 });
    expect(buildCandidateQuery(withFilters({ projectId: 9, showAllProjects: true }), 7, NOW)).toEqual({ project_id: 9 });
  });

  test('period resolves to start/end with the date basis', () => {
    const query = buildCandidateQuery(withFilters({ period: { preset: 'this_month' }, dateBasis: 'invoiced' }), null, NOW);
    expect(query).toEqual({ start: '2026-09-01', end: '2026-09-30', date_basis: 'invoiced' });
  });

  test('custom open range sends only the given bound', () => {
    const query = buildCandidateQuery(withFilters({ period: { preset: 'custom', start: '2026-03-01' } }), null, NOW);
    expect(query).toEqual({ start: '2026-03-01', date_basis: 'spent' });
  });

  test('category, statuses and missing evidence map to server params', () => {
    const query = buildCandidateQuery(
      withFilters({ categoryId: 3, statuses: ['spent', 'invoiced'], evidence: 'missing' }),
      null,
      NOW,
    );
    expect(query).toEqual({ category_id: 3, status: ['spent', 'invoiced'], missing: true });
  });

  test('complete evidence is not sent to the server', () => {
    expect(buildCandidateQuery(withFilters({ evidence: 'complete' }), null, NOW)).toEqual({});
  });
});

describe('hasActiveFilters', () => {
  test('defaults and the default batch project limit are not active filters', () => {
    expect(hasActiveFilters(DEFAULT_CANDIDATE_FILTERS)).toBe(false);
    expect(hasActiveFilters(withFilters({ showAllProjects: true }))).toBe(false);
  });

  test('any explicit filter is active', () => {
    expect(hasActiveFilters(withFilters({ search: 'a' }))).toBe(true);
    expect(hasActiveFilters(withFilters({ period: { preset: 'this_year' } }))).toBe(true);
    expect(hasActiveFilters(withFilters({ categoryId: 1 }))).toBe(true);
    expect(hasActiveFilters(withFilters({ projectId: 1 }))).toBe(true);
    expect(hasActiveFilters(withFilters({ statuses: ['spent'] }))).toBe(true);
    expect(hasActiveFilters(withFilters({ evidence: 'missing' }))).toBe(true);
  });
});
