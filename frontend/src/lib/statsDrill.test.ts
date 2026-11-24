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
    expect(statsCellLink({ ...base, groupBy: 'travel_scope', row: row('nonlocal', '市外'), status: null })).toContain('travel_scope=nonlocal');
    const month = new URL(statsCellLink({ ...base, groupBy: 'month', row: row('2026-02'), status: null }), 'http://x');
    expect(month.searchParams.get('start')).toBe('2026-02-01');
    expect(month.searchParams.get('end')).toBe('2026-02-28');
  });

  test('non-numeric or malformed keys do not add filters', () => {
    expect(statsCellLink({ ...base, groupBy: 'category', row: row('none'), status: null })).toContain('uncategorized=true');
    expect(statsCellLink({ ...base, groupBy: 'month', row: row('2026-13'), status: null })).toContain('start=2026-07-01');
    expect(statsCellLink({ ...base, groupBy: 'month', row: row('bad'), status: null })).toContain('start=2026-07-01');
  });

  test('cross dimension and unbatched cells drill through', () => {
    const batch = statsCellLink({
      ...base,
      groupBy: 'category',
      row: row('3', '易耗品'),
      status: null,
      crossBy: 'batch',
      column: { key: '9', label: '九月批次' },
    });
    expect(batch).toContain('category_id=3');
    expect(batch).toContain('batch_id=9');
    const unbatched = statsCellLink({
      ...base,
      groupBy: 'lab_platform',
      row: row('required', '需要平台申请'),
      status: null,
      crossBy: 'batch',
      column: { key: 'none', label: '未分批' },
    });
    expect(unbatched).toContain('lab_platform=required');
    expect(unbatched).toContain('unbatched=true');
    expect(statsCellLink({
      ...base,
      groupBy: 'lab_platform',
      row: row('none', '未判定'),
      status: null,
    })).toContain('uncategorized=true');
  });
});
