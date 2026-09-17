import { describe, expect, test } from 'vitest';
import { decodeExpenseFilters, encodeExpenseFilters, expensesLink, filtersToQuery } from './expenseFilters';

const NOW = new Date('2026-09-17T02:00:00Z');

describe('expense filters', () => {
  test('decodes URL params with validation', () => {
    const filters = decodeExpenseFilters(
      new URLSearchParams('period=this_month&date_basis=sent&category_id=3&project_id=abc&status=spent,bogus&q=京东&batch_id=7&unbatched=true&missing=true'),
    );
    expect(filters).toEqual({
      period: { preset: 'this_month' },
      dateBasis: 'sent',
      categoryId: 3,
      projectId: null,
      statuses: ['spent'],
      q: '京东',
      batchId: 7,
      unbatched: true,
      missingOnly: true,
    });
  });

  test('defaults when empty', () => {
    const filters = decodeExpenseFilters(new URLSearchParams());
    expect(filters.dateBasis).toBe('spent');
    expect(filters.period.preset).toBe('this_year');
    expect(filters.statuses).toEqual([]);
  });

  test('round-trips through encode', () => {
    const params = new URLSearchParams('period=custom&start=2026-01-01&end=2026-03-31&status=sent,void&q=abc');
    const encoded = encodeExpenseFilters(decodeExpenseFilters(params));
    expect(decodeExpenseFilters(encoded)).toEqual(decodeExpenseFilters(params));
    expect(encoded.has('date_basis')).toBe(false);
  });

  test('builds API query', () => {
    const query = filtersToQuery(decodeExpenseFilters(new URLSearchParams('period=this_quarter&status=spent&q=%20x%20&category_id=2&project_id=4&batch_id=9&unbatched=true&missing=true')), NOW);
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
      page: 1,
      page_size: 200,
    });
  });

  test('expensesLink starts from all-time filters', () => {
    expect(expensesLink({ missingOnly: true })).toBe('/expenses?period=all&missing=true');
    expect(expensesLink({ statuses: ['spent'] })).toBe('/expenses?period=all&status=spent');
  });
});
