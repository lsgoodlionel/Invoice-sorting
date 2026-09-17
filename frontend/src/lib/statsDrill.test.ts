import { describe, expect, test } from 'vitest';
import type { StatsRow } from '../api/types';
import { statsCellLink } from './statsDrill';

const row = (key: string, label = key): StatsRow => ({ key, label, by_status: {}, total_cents: 0 });
const base = { start: '2026-07-01', end: '2026-09-30', dateBasis: 'spent' as const };

describe('statsCellLink', () => {
  test('category cell carries period, status and category', () => {
    const url = new URL(statsCellLink({ ...base, groupBy: 'category', row: row('3', '易耗品'), status: 'sent' }), 'http://x');
    expect(url.pathname).toBe('/expenses');
    expect(Object.fromEntries(url.searchParams)).toEqual({ period: 'custom', start: '2026-07-01', end: '2026-09-30', category_id: '3', status: 'sent' });
  });

  test('project, merchant and month groups', () => {
    expect(statsCellLink({ ...base, groupBy: 'project', row: row('4'), status: null })).toContain('project_id=4');
    expect(statsCellLink({ ...base, groupBy: 'merchant', row: row('m', '腾讯云'), status: null })).toContain(`q=${encodeURIComponent('腾讯云')}`);
    const month = new URL(statsCellLink({ ...base, groupBy: 'month', row: row('2026-02'), status: null }), 'http://x');
    expect(month.searchParams.get('start')).toBe('2026-02-01');
    expect(month.searchParams.get('end')).toBe('2026-02-28');
  });

  test('non-numeric or malformed keys do not add filters', () => {
    expect(statsCellLink({ ...base, groupBy: 'category', row: row('none'), status: null })).not.toContain('category_id');
    expect(statsCellLink({ ...base, groupBy: 'month', row: row('2026-13'), status: null })).toContain('start=2026-07-01');
    expect(statsCellLink({ ...base, groupBy: 'month', row: row('bad'), status: null })).toContain('start=2026-07-01');
  });
});
