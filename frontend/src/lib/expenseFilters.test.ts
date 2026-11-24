import { describe, expect, test } from 'vitest';
import { decodeExpenseFilters, encodeExpenseFilters, expenseDetailLink, expensesLink, filtersToQuery, parseOpenExpenseId } from './expenseFilters';

const NOW = new Date('2026-09-17T02:00:00Z');

describe('expense filters', () => {
  test('decodes URL params with validation', () => {
    const filters = decodeExpenseFilters(
      new URLSearchParams('period=this_month&date_basis=sent&category_id=3&project_id=abc&status=spent,bogus&q=京东&batch_id=7&unbatched=true&missing=true&travel_scope=nonlocal'),
    );
    expect(filters).toEqual({
      period: { preset: 'this_month' },
      dateBasis: 'sent',
      categoryId: 3,
      uncategorized: false,
      projectId: null,
      statuses: ['spent'],
      q: '京东',
      batchId: 7,
      unbatched: true,
      missingOnly: true,
      travelScope: 'nonlocal',
      requiresLabPlatform: null,
      sortBy: 'date',
      sortOrder: 'desc',
      page: 1,
      pageSize: 10,
    });
  });

  test('defaults when empty', () => {
    const filters = decodeExpenseFilters(new URLSearchParams());
    expect(filters.dateBasis).toBe('spent');
    expect(filters.period.preset).toBe('this_year');
    expect(filters.statuses).toEqual(['spent', 'invoiced', 'complete']);
  });

  test('round-trips through encode', () => {
    const params = new URLSearchParams('period=custom&start=2026-01-01&end=2026-03-31&status=sent,void&q=abc');
    const encoded = encodeExpenseFilters(decodeExpenseFilters(params));
    expect(decodeExpenseFilters(encoded)).toEqual(decodeExpenseFilters(params));
    expect(encoded.has('date_basis')).toBe(false);
  });

  test('round-trips platform, uncategorized and sorting filters', () => {
    const filters = decodeExpenseFilters(new URLSearchParams('lab_platform=required&uncategorized=true&sort_by=status&sort_order=asc'));
    expect(filters.requiresLabPlatform).toBe(true);
    expect(filters.uncategorized).toBe(true);
    expect(filters.sortBy).toBe('status');
    expect(filters.sortOrder).toBe('asc');
    expect(decodeExpenseFilters(encodeExpenseFilters(filters))).toEqual(filters);
  });

  test('builds API query', () => {
    const query = filtersToQuery(decodeExpenseFilters(new URLSearchParams('period=this_quarter&status=spent&q=%20x%20&category_id=2&project_id=4&batch_id=9&unbatched=true&missing=true&travel_scope=local')), NOW);
    expect(query).toEqual({
      start: '2026-07-01',
      end: '2026-09-30',
      date_basis: 'spent',
      category_id: 2,
      project_id: 4,
      status: ['spent'],
      q: 'x',
      batch_id: 9,
      unbatched: true,
      missing: true,
      travel_scope: 'local',
      sort_by: 'date',
      sort_order: 'desc',
      page: 1,
      page_size: 10,
    });
  });

  test('supports page sizes and the unbounded all option', () => {
    const paged = decodeExpenseFilters(new URLSearchParams('page=3&page_size=40'));
    expect(filtersToQuery(paged, NOW)).toMatchObject({ page: 3, page_size: 40 });
    const all = decodeExpenseFilters(new URLSearchParams('page=8&page_size=all'));
    expect(filtersToQuery(all, NOW)).toMatchObject({ page: 1, all: true });
    expect(filtersToQuery(all, NOW)).not.toHaveProperty('page_size');
  });

  test('expensesLink starts from all-time filters', () => {
    expect(expensesLink({ missingOnly: true })).toBe('/expenses?period=all&missing=true');
    expect(expensesLink({ statuses: ['spent'] })).toBe('/expenses?period=all&status=spent');
  });

  test('expenseDetailLink opens a record drawer via the open param', () => {
    expect(expenseDetailLink(12)).toBe('/expenses?period=all&open=12');
    expect(parseOpenExpenseId(new URLSearchParams('open=12'))).toBe(12);
    expect(parseOpenExpenseId(new URLSearchParams('open=abc'))).toBeNull();
    expect(parseOpenExpenseId(new URLSearchParams(''))).toBeNull();
  });
});
